"""沿街寻位逻辑 —— 模拟真实驾驶员在 CBD 内沿道路找车位的行为。

真实驾驶行为：
- 沿当前道路缓行，观察前方路侧是否有空车位
- 看到空位则尝试停入（有一定概率看漏）
- 快走到路尽头时随机拐弯/换路继续找
- 不会站在路口扫视半径 80 米内的所有道路
"""
import random
import traci
import traci.exceptions

from config import (
    SIGHT_DISTANCE, SPOT_STOP_MARGIN, PARKING_DURATION, INTERSECTION_LOOKAHEAD,
)


def reroute_to_cbd(vid, cbd_edges):
    """分配随机 CBD 边作为新目的地，让车辆沿路网自然巡航。"""
    if not cbd_edges:
        return False
    try:
        current = traci.vehicle.getRoadID(vid)
    except traci.exceptions.TraCIException:
        return False
    candidates = [e for e in cbd_edges if e != current]
    if not candidates:
        candidates = cbd_edges
    try:
        traci.vehicle.changeTarget(vid, random.choice(candidates))
        return True
    except traci.exceptions.TraCIException:
        return False


def scan_street(vid, current_edge, current_lanepos, spots_by_edge, all_spots,
                opposite_map=None, outgoing_map=None, edge_lengths=None):
    """沿街 + 路口张望空车位（模拟真实驾驶员视野）。

    视野分层：
    - 直道行驶：当前道路本侧 + 对向车道
    - 接近路口（距路口 ≤ INTERSECTION_LOOKAHEAD）：额外扫视交叉方向
      所有可达边及其对向车道（最多 8 条边）
    - 视角始终在路上：只扫前方及路口方向，不扫背后

    返回: (spot_id, spot_edge) 或 (None, None)
    """
    candidates = []
    if opposite_map is None:
        opposite_map = {}
    if outgoing_map is None:
        outgoing_map = {}
    if edge_lengths is None:
        edge_lengths = {}

    def _add_edge_spots(edge_id, base_dist):
        for sid in spots_by_edge.get(edge_id, []):
            if all_spots[sid]["occupied"] >= all_spots[sid]["capacity"]:
                continue
            spot_pos = all_spots[sid].get("startPos", 0.0)
            ahead = base_dist + spot_pos
            if SPOT_STOP_MARGIN <= ahead <= SIGHT_DISTANCE:
                candidates.append((sid, edge_id, ahead))

    def _add_edge_with_opposite(edge_id, base_dist):
        _add_edge_spots(edge_id, base_dist)
        opp = opposite_map.get(edge_id)
        if opp:
            _add_edge_spots(opp, base_dist + 15.0)

    # 1. 当前道路：本侧 + 对向
    _add_edge_with_opposite(current_edge, -current_lanepos)

    # 2. 计算距路口距离
    edge_len = edge_lengths.get(current_edge, 100.0)
    if current_edge.startswith(":"):
        edge_len = 15.0
    dist_to_end = edge_len - current_lanepos

    # 3. 如果接近路口 → 扫视交叉方向所有可达边
    if 0 < dist_to_end <= INTERSECTION_LOOKAHEAD:
        for out_edge in outgoing_map.get(current_edge, []):
            # 交叉方向的边从路口起算，spot 越靠近路口越近
            _add_edge_with_opposite(out_edge, dist_to_end)

    # 4. 下一条路（路由前方）及其对向
    if not candidates:
        try:
            route = traci.vehicle.getRoute(vid)
            idx = traci.vehicle.getRouteIndex(vid)
            if idx + 1 < len(route):
                nxt = route[idx + 1]
                _add_edge_with_opposite(nxt, SIGHT_DISTANCE - 20.0)
        except traci.exceptions.TraCIException:
            pass

    if not candidates:
        return None, None

    candidates.sort(key=lambda x: x[2])
    for sid, edge, dist in candidates:
        prob = 0.90 if dist < 40 else 0.60
        if random.random() < prob:
            return sid, edge
    return None, None


def try_park(vid, spot_id, spot_edge, stats, current_edge, current_lanepos, all_spots):
    """尝试停入指定车位。车位在下一道路时先 changeTarget 延后处理。"""
    if spot_edge == current_edge:
        spot_pos = all_spots[spot_id].get("startPos", 0.0)
        if spot_pos < current_lanepos + SPOT_STOP_MARGIN:
            return False
        if all_spots[spot_id]["occupied"] < all_spots[spot_id]["capacity"]:
            try:
                traci.vehicle.setParkingAreaStop(vid, spot_id, duration=PARKING_DURATION)
                stats["target_spot"] = spot_id
                return True
            except traci.exceptions.TraCIException:
                return False
    else:
        try:
            traci.vehicle.changeTarget(vid, spot_edge)
            stats["pending_spot"] = spot_id
            stats["pending_spot_edge"] = spot_edge
            return True
        except traci.exceptions.TraCIException:
            return False
    return False


def check_pending(vid, stats, current_edge, current_lanepos, all_spots):
    """车辆已到达 pending 车位所在道路，尝试停入。"""
    pending = stats.get("pending_spot")
    if not pending:
        return
    if stats.get("pending_spot_edge") != current_edge:
        return
    spot_pos = all_spots[pending].get("startPos", 0.0)
    if spot_pos < current_lanepos + SPOT_STOP_MARGIN:
        stats.pop("pending_spot", None)
        stats.pop("pending_spot_edge", None)
        return
    if all_spots[pending]["occupied"] < all_spots[pending]["capacity"]:
        try:
            traci.vehicle.setParkingAreaStop(vid, pending, duration=PARKING_DURATION)
            stats["target_spot"] = pending
            stats.pop("pending_spot", None)
            stats.pop("pending_spot_edge", None)
        except traci.exceptions.TraCIException:
            stats.pop("target_spot", None)
            stats.pop("pending_spot", None)
            stats.pop("pending_spot_edge", None)
    else:
        stats.pop("pending_spot", None)
        stats.pop("pending_spot_edge", None)


def handle_occupied(vid, stats, current_edge, current_lanepos, all_spots, target_edges):
    """已锁定车位被抢占时放弃并重新巡航。"""
    target = stats["target_spot"]
    if all_spots[target]["edge"] != current_edge:
        return
    if all_spots[target]["occupied"] >= all_spots[target]["capacity"]:
        if current_lanepos <= all_spots[target].get("startPos", 0.0):
            try:
                traci.vehicle.setParkingAreaStop(vid, target, duration=0)
            except traci.exceptions.TraCIException:
                pass
        else:
            try:
                traci.vehicle.resume(vid)
            except traci.exceptions.TraCIException:
                pass
        stats["target_spot"] = None
        reroute_to_cbd(vid, target_edges)
