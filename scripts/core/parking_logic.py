"""沿街寻位逻辑 —— 模拟真实驾驶员在路网中沿道路找车位的行为。

核心原则：不自行判定车辆"已驶过"或"距离不够"——
停入是否可行完全交给 SUMO 的 setParkingAreaStop 决定。
"""

import random

import traci
import traci.exceptions
from .config import (
    INTERSECTION_LOOKAHEAD,
    PARKING_DURATION,
    SIGHT_DISTANCE,
    SPOT_STOP_MARGIN,
)


def reroute_random(vid, all_edges, opposite_map=None, outgoing_map=None):
    """分配随机边作为新目的地。排除当前边、对向边及直接相邻边，确保路由不短于 2 跳。"""
    if not all_edges:
        return False
    try:
        current = traci.vehicle.getRoadID(vid)
    except traci.exceptions.TraCIException:
        return False

    exclude = {current}
    if opposite_map:
        opp = opposite_map.get(current)
        if opp:
            exclude.add(opp)
    if outgoing_map:
        for e in outgoing_map.get(current, []):
            exclude.add(e)

    candidates = [e for e in all_edges if e not in exclude]
    if not candidates:
        candidates = [e for e in all_edges if e != current]
    try:
        traci.vehicle.changeTarget(vid, random.choice(candidates))
        return True
    except traci.exceptions.TraCIException:
        return False


def scan_street(
    vid,
    current_edge,
    current_lanepos,
    spots_by_edge,
    all_spots,
    opposite_map=None,
    outgoing_map=None,
    edge_lengths=None,
    full_scan=True,
):
    """沿街 + 路口张望空车位。返回 (spot_id, spot_edge) 或 (None, None)。"""
    candidates = []
    if opposite_map is None:
        opposite_map = {}
    if outgoing_map is None:
        outgoing_map = {}
    if edge_lengths is None:
        edge_lengths = {}

    def _add_spots(edge_id, base_dist, min_ahead):
        for sid in spots_by_edge.get(edge_id, []):
            if all_spots[sid]["occupied"] >= all_spots[sid]["capacity"]:
                continue
            spot_pos = all_spots[sid].get("startPos", 0.0)
            ahead = base_dist + spot_pos
            if min_ahead <= ahead <= SIGHT_DISTANCE:
                candidates.append((sid, edge_id, ahead))

    def _add_with_opp(edge_id, base_dist, min_ahead):
        _add_spots(edge_id, base_dist, min_ahead)
        opp = opposite_map.get(edge_id)
        if not opp:
            return

        fwd_len = edge_lengths.get(edge_id, 100.0)
        opp_len = edge_lengths.get(opp, fwd_len)

        for sid in spots_by_edge.get(opp, []):
            if all_spots[sid]["occupied"] >= all_spots[sid]["capacity"]:
                continue
            spot_pos = all_spots[sid].get("startPos", 0.0)

            if base_dist < 0:
                # 车辆在当前道路上 → 可从前方或后方路口掉头
                dist_front = (fwd_len + base_dist) + spot_pos
                dist_rear = (-base_dist) + (opp_len - spot_pos)
                ahead = dist_front if dist_front < dist_rear else dist_rear
            else:
                # 对向道路近端就在路口，可从路口直接进入
                ahead = base_dist + (opp_len - spot_pos)

            if min_ahead <= ahead <= SIGHT_DISTANCE:
                candidates.append((sid, opp, ahead))

    # 每步必扫：当前道路本侧 + 对向
    _add_with_opp(current_edge, -current_lanepos, min_ahead=0)

    # full_scan：路口交叉方向 + 下一条路
    if full_scan:
        edge_len = edge_lengths.get(current_edge, 100.0)
        if current_edge.startswith(":"):
            edge_len = 15.0
        dist_to_end = edge_len - current_lanepos

        if 0 < dist_to_end <= INTERSECTION_LOOKAHEAD:
            for out_edge in outgoing_map.get(current_edge, []):
                _add_with_opp(out_edge, dist_to_end, min_ahead=SPOT_STOP_MARGIN)

        if not candidates:
            try:
                route = traci.vehicle.getRoute(vid)
                idx = traci.vehicle.getRouteIndex(vid)
                if idx + 1 < len(route):
                    nxt = route[idx + 1]
                    _add_with_opp(
                        nxt, SIGHT_DISTANCE - 20.0, min_ahead=SPOT_STOP_MARGIN
                    )
            except traci.exceptions.TraCIException:
                pass

    if not candidates:
        return None, None

    candidates.sort(key=lambda x: x[2])
    for sid, edge, dist in candidates:
        if edge == current_edge:
            prob = 1.0 if dist < 40 else 0.95
        else:
            prob = 0.85 if dist < 40 else 0.65
        if random.random() < prob:
            return sid, edge
    return None, None


def try_park(vid, spot_id, spot_edge, stats, current_edge, all_spots):
    """
    尝试停入车位。
    当前道路 → setParkingAreaStop。
    其他道路 → changeTarget + pending，已有承诺时拒绝新车位。
    """
    if spot_id not in all_spots:
        return False
    if spot_edge == current_edge:
        if all_spots[spot_id]["occupied"] < all_spots[spot_id]["capacity"]:
            try:
                traci.vehicle.setParkingAreaStop(
                    vid, spot_id, duration=PARKING_DURATION
                )
                stats["target_spot"] = spot_id
                stats.pop("pending_spot", None)
                stats.pop("pending_spot_edge", None)
                return True
            except traci.exceptions.TraCIException:
                return False
    else:
        if stats.get("pending_spot"):
            return False
        try:
            traci.vehicle.changeTarget(vid, spot_edge)
            stats["pending_spot"] = spot_id
            stats["pending_spot_edge"] = spot_edge
            return True
        except traci.exceptions.TraCIException:
            return False
    return False


def check_pending(vid, stats, current_edge, all_spots, all_edges,
                  opposite_map=None, outgoing_map=None):
    """到达 pending 边后尝试停入。"""
    pending = stats.get("pending_spot")
    if not pending:
        return
    if stats.get("pending_spot_edge") != current_edge:
        return
    if pending not in all_spots:
        stats.pop("pending_spot", None)
        stats.pop("pending_spot_edge", None)
        reroute_random(vid, all_edges, opposite_map, outgoing_map)
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
            reroute_random(vid, all_edges, opposite_map, outgoing_map)
    else:
        stats.pop("pending_spot", None)
        stats.pop("pending_spot_edge", None)
        reroute_random(vid, all_edges, opposite_map, outgoing_map)


def handle_occupied(vid, stats, current_edge, all_spots, all_edges,
                    opposite_map=None, outgoing_map=None):
    """车位被占或车辆已离开目标道路时放弃。"""
    target = stats.get("target_spot")
    if not target or target not in all_spots:
        stats["target_spot"] = None
        reroute_random(vid, all_edges, opposite_map, outgoing_map)
        return
    target_edge = all_spots[target]["edge"]
    if target_edge != current_edge:
        # 不在目标边：若不是途经路口，说明已离开该道路
        if not current_edge.startswith(":"):
            try:
                traci.vehicle.setParkingAreaStop(vid, target, duration=0)
            except traci.exceptions.TraCIException:
                pass
            stats["target_spot"] = None
            reroute_random(vid, all_edges, opposite_map, outgoing_map)
        return
    if all_spots[target]["occupied"] >= all_spots[target]["capacity"]:
        try:
            traci.vehicle.setParkingAreaStop(vid, target, duration=0)
        except traci.exceptions.TraCIException:
            pass
        stats["target_spot"] = None
        reroute_random(vid, all_edges, opposite_map, outgoing_map)
