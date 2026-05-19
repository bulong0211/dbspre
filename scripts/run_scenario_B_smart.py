"""场景 B —— 智能预订 + 动态定价模式。"""

import heapq
import math
import xml.etree.ElementTree as ET

import traci
import traci.constants as tc
import traci.exceptions
from core.config import (
    CONFIG_DIR,
    DB_SYNC_INTERVAL,
    ENABLE_SCREEN_RECORDING,
    PLOTTER_UPDATE_INTERVAL,
    SCENARIO_B_NAME,
    SIMULATION_DURATION_LIMIT,
    STREET_SPOT_THRESHOLD,
    TOTAL_VEHICLES_TARGET,
    UNIT_DIST_COST,
    sumoCmd,
)
from core.connection import get_db_connection
from core.db_ops import log_cruise, log_run_summary, sync_spots_priced
from core.emissions import (
    EMISSION_SUB_VARS,
    accumulate_environment,
    environment_log_values,
    init_environment_stats,
)
from core.gui_tracker import GUITracker
from core.monitor import MultiprocessingPlotter
from core.recording import prepare_visual_session
from core.reset_db import reset_database


# ---------------------------------------------------------------------------
# 静态数据加载
# ---------------------------------------------------------------------------
def _load_spots(cursor):
    """读取场景 B 所需的车位容量、基础价格和当前价格。"""
    cursor.execute(
        "SELECT spot_id, edge_id, capacity, base_price, current_price FROM Parking_Spots"
    )
    spots = {}
    for row in cursor.fetchall():
        spots[row[0]] = {
            "edge": row[1],
            "capacity": row[2],
            "booked": 0,
            "base_price": float(row[3]),
            "current_price": float(row[4]),
            "pos": None,
            "lane_index": 0,
            "stop_pos": None,
        }
    return spots


def _compute_positions(all_spots):
    """获取所有停车位的物理坐标（需在 traci.start 之后调用）。"""
    for sid, data in all_spots.items():
        try:
            lane_id = traci.parkingarea.getLaneID(sid)
            start_pos = traci.parkingarea.getStartPos(sid)
            end_pos = traci.parkingarea.getEndPos(sid)
            lane_index = int(lane_id.rsplit("_", 1)[1])
            data["lane_index"] = lane_index
            data["stop_pos"] = (start_pos + end_pos) / 2.0
            data["pos"] = traci.lane.getShape(lane_id)[0]
        except traci.exceptions.TraCIException:
            lane_id = f"{data['edge']}_0"
            try:
                data["stop_pos"] = traci.lane.getLength(lane_id) / 2.0
                data["pos"] = traci.lane.getShape(lane_id)[0]
            except traci.exceptions.TraCIException:
                data["stop_pos"] = 0.0
                data["pos"] = (0, 0)


def _load_edge_graph():
    """从 SUMO net.xml 读取本地有向路网，供场景 B 快速估算路网距离。"""
    tree = ET.parse(CONFIG_DIR / "demo.net.xml")
    nodes = {
        n.attrib["id"]: (float(n.attrib["x"]), float(n.attrib["y"]))
        for n in tree.getroot().findall("junction")
    }
    edges = {}
    graph = {}

    for edge in tree.getroot().findall("edge"):
        if "function" in edge.attrib:
            continue

        eid = edge.attrib["id"]
        from_node = edge.attrib.get("from")
        to_node = edge.attrib.get("to")
        if from_node not in nodes or to_node not in nodes:
            continue

        length = None
        lane = edge.find("lane")
        if lane is not None and "length" in lane.attrib:
            length = float(lane.attrib["length"])
        if length is None:
            fx, fy = nodes[from_node]
            tx, ty = nodes[to_node]
            length = math.hypot(tx - fx, ty - fy)

        edges[eid] = {
            "from_node": from_node,
            "to_node": to_node,
            "length": length,
        }
        graph.setdefault(from_node, []).append((to_node, length))

    return edges, graph


def _shortest_node_distances(start_node, graph):
    """单源 Dijkstra；每辆新车只计算一次，再复用到所有候选车位。"""
    distances = {start_node: 0.0}
    heap = [(0.0, start_node)]

    while heap:
        current_dist, node = heapq.heappop(heap)
        if current_dist > distances[node]:
            continue
        for next_node, edge_len in graph.get(node, []):
            next_dist = current_dist + edge_len
            if next_dist < distances.get(next_node, float("inf")):
                distances[next_node] = next_dist
                heapq.heappush(heap, (next_dist, next_node))

    return distances


def _fallback_euclidean_distance(vehicle_pos, sp):
    """在缺少路网拓扑时使用直线距离作为保底估算。"""
    return math.hypot(vehicle_pos[0] - sp["pos"][0], vehicle_pos[1] - sp["pos"][1])


def _fallback_candidate_distances(vid, all_spots):
    """为所有未满车位生成直线距离候选表。"""
    try:
        vehicle_pos = traci.vehicle.getPosition(vid)
    except traci.exceptions.TraCIException:
        return {}
    return {
        sid: _fallback_euclidean_distance(vehicle_pos, sp)
        for sid, sp in all_spots.items()
        if sp["booked"] < sp["capacity"]
    }


def _candidate_distances(vid, all_spots, edge_data, graph):
    """估算车辆到各目标边停车位置的路网行驶距离。"""
    try:
        current_edge = traci.vehicle.getRoadID(vid)
        current_pos = traci.vehicle.getLanePosition(vid)
    except traci.exceptions.TraCIException:
        return {}

    current = edge_data.get(current_edge)
    if current is None:
        return _fallback_candidate_distances(vid, all_spots)

    remaining_current = max(0.0, current["length"] - current_pos)
    node_distances = _shortest_node_distances(current["to_node"], graph)
    result = {}
    vehicle_pos = None

    for sid, sp in all_spots.items():
        if sp["booked"] >= sp["capacity"]:
            continue

        target = edge_data.get(sp["edge"])
        if target is None:
            if vehicle_pos is None:
                try:
                    vehicle_pos = traci.vehicle.getPosition(vid)
                except traci.exceptions.TraCIException:
                    continue
            result[sid] = _fallback_euclidean_distance(vehicle_pos, sp)
            continue

        stop_pos = max(0.0, sp["stop_pos"] or 0.0)
        if sp["edge"] == current_edge and stop_pos >= current_pos:
            result[sid] = stop_pos - current_pos
            continue

        node_dist = node_distances.get(target["from_node"])
        if node_dist is None:
            continue

        result[sid] = remaining_current + node_dist + stop_pos

    return result


# ---------------------------------------------------------------------------
# 浪涌定价
# ---------------------------------------------------------------------------
def _build_pricing_index(all_spots):
    """预计算动态定价分组，避免每个仿真步重复构造街道聚合字典。"""
    street_groups = {}
    lot_spots = []

    for sid, data in all_spots.items():
        if data["capacity"] <= STREET_SPOT_THRESHOLD:
            eid = data["edge"]
            if eid not in street_groups:
                street_groups[eid] = {"spot_ids": [], "total_capacity": 0}
            street_groups[eid]["spot_ids"].append(sid)
            street_groups[eid]["total_capacity"] += data["capacity"]
        else:
            lot_spots.append(sid)

    return street_groups, lot_spots


def _price_from_rate(base_price, rate):
    """根据占用率阶梯计算动态价格。"""
    if rate > 0.90:
        return base_price * 2.0
    if rate > 0.70:
        return base_price * 1.5
    return base_price


def _compute_pricing(all_spots, pricing_index):
    """按街道维度聚合小容量路边车位，依据占用率阶梯式涨价。"""
    street_groups, lot_spots = pricing_index

    for sid in lot_spots:
        data = all_spots[sid]
        rate = data["booked"] / data["capacity"]
        data["current_price"] = _price_from_rate(data["base_price"], rate)

    for group in street_groups.values():
        total_booked = sum(all_spots[sid]["booked"] for sid in group["spot_ids"])
        rate = total_booked / group["total_capacity"]
        for sid in group["spot_ids"]:
            data = all_spots[sid]
            data["current_price"] = _price_from_rate(data["base_price"], rate)


# ---------------------------------------------------------------------------
# 车辆分配
# ---------------------------------------------------------------------------
def _find_best_spot(vid, all_spots, edge_data, graph):
    """按统一货币成本选择最优车位。"""
    distances = _candidate_distances(vid, all_spots, edge_data, graph)
    if not distances:
        return None

    best = None
    min_cost = float("inf")
    for sid, dist in distances.items():
        sp = all_spots[sid]
        cost = sp["current_price"] + (dist * UNIT_DIST_COST)
        if cost < min_cost:
            min_cost = cost
            best = sid
    return best


def _assign_vehicle(vid, spot_id, all_spots, veh_stats, current_time):
    """将车辆分配至指定车位并初始化追踪状态。"""
    edge_id = all_spots[spot_id]["edge"]

    traci.vehicle.changeTarget(vid, edge_id)
    traci.vehicle.setParkingAreaStop(vid, spot_id, duration=360000.0)
    traci.vehicle.subscribe(vid, [tc.VAR_DISTANCE, tc.VAR_SPEED, *EMISSION_SUB_VARS])

    # 所有 TraCI 调用成功后才更新预订计数
    all_spots[spot_id]["booked"] += 1

    stats = {
        "status": "driving",
        "target_spot": spot_id,
        "spawn_time": current_time,
        "search_time": 0.0,
        "last_dist": 0.0,
        "speed": 0.0,
    }
    stats.update(init_environment_stats())
    veh_stats[vid] = stats


# ---------------------------------------------------------------------------
# 车辆处理
# ---------------------------------------------------------------------------
def _settle(vid, stats, current_time, spot_id, cursor, conn):
    """结算车辆行驶日志。"""
    stats["search_time"] = current_time - stats["spawn_time"]
    env = environment_log_values(stats)
    log_cruise(
        cursor,
        vid,
        SCENARIO_B_NAME,
        stats["search_time"],
        0,  # 场景B为预订模式，不存在巡航绕圈行为
        env["total_fuel"],
        spot_id,
        env["total_co2"],
        env["total_nox"],
        env["total_pmx"],
    )
    conn.commit()


def _handle_departed(
    departed, all_spots, veh_stats, active_driving, current_time, edge_data, graph
):
    """新生成车辆：分配车位 → 初始化状态。"""
    booked_any = False

    for vid in departed:
        try:
            traci.vehicle.setShapeClass(vid, "passenger")
        except traci.exceptions.TraCIException:
            continue

        spot_id = _find_best_spot(vid, all_spots, edge_data, graph)
        if spot_id is None:
            traci.simulation.writeMessage(f"⚠️ [系统爆满] 车辆 {vid} 无法分配到车位！")
            continue

        try:
            _assign_vehicle(vid, spot_id, all_spots, veh_stats, current_time)
            active_driving.add(vid)
            booked_any = True
        except traci.exceptions.TraCIException:
            traci.simulation.writeMessage(
                f"⚠️ [分配失败] 车辆 {vid} 路由至 {spot_id} 失败"
            )

    return booked_any


def _process_driving(
    active_driving, veh_stats, sub_results, current_time, cursor, conn, gui
):
    """行驶中车辆：指标更新、消失检测、泊车结算。"""
    completed = 0
    teleported = 0

    for vid in list(active_driving):
        stats = veh_stats.get(vid)
        if stats is None or stats["status"] != "driving":
            active_driving.discard(vid)
            continue

        # 车辆从路网中消失
        if vid not in sub_results:
            stats["status"] = "teleported"
            active_driving.discard(vid)
            teleported += 1
            _settle(vid, stats, current_time, None, cursor, conn)
            continue

        # 累计指标
        data = sub_results[vid]
        stats["last_dist"] = data[tc.VAR_DISTANCE]
        accumulate_environment(stats, data)
        stats["speed"] = data[tc.VAR_SPEED]

        # 检测是否已停好
        try:
            if traci.vehicle.isStoppedParking(vid):
                target = stats["target_spot"]
                stats["status"] = "parked"
                active_driving.discard(vid)
                _settle(vid, stats, current_time, target, cursor, conn)
                try:
                    traci.vehicle.unsubscribe(vid)
                except traci.exceptions.TraCIException:
                    pass

                if gui and vid == gui.current_protagonist:
                    traci.simulation.writeMessage(
                        f"🎉 车辆 {vid} 停好了！\n✅ 最终落脚点: {target}"
                    )
                    gui.on_vehicle_parked(vid)
                completed += 1
        except traci.exceptions.TraCIException:
            pass

    return completed, teleported


# ---------------------------------------------------------------------------
# 主仿真循环
# ---------------------------------------------------------------------------
def run_smart_booking_with_pricing():
    """运行场景 B 的智能预订与动态定价仿真。"""
    print("🔄 准备仿真环境...")
    reset_database(clear_logs=False, scenario_to_clear=SCENARIO_B_NAME)

    print("🔌 正在连接数据库...")
    conn = get_db_connection()
    cursor = conn.cursor()

    all_spots = _load_spots(cursor)
    pricing_index = _build_pricing_index(all_spots)
    edge_data, graph = _load_edge_graph()

    print("🚀 启动场景 B (动态定价 + 智能预订模式) - 最大限时 2 小时...")
    traci.start(sumoCmd)
    _compute_positions(all_spots)

    gui = GUITracker()
    plotter = MultiprocessingPlotter("场景 B - 智能预订监控面板", layout="B")
    recorder = None

    try:
        recorder = prepare_visual_session(SCENARIO_B_NAME, ENABLE_SCREEN_RECORDING)

        veh_stats = {}
        active_driving = set()
        completed = 0
        teleported = 0
        current_time = 0
        pricing_dirty = True

        while (
            traci.simulation.getMinExpectedNumber() > 0
            and current_time < SIMULATION_DURATION_LIMIT
        ):
            traci.simulationStep()
            current_time = traci.simulation.getTime()

            gui.update(active_driving, veh_stats, current_time)

            # 新车初始化
            departed = traci.simulation.getDepartedIDList()
            if departed:
                if pricing_dirty:
                    _compute_pricing(all_spots, pricing_index)
                    pricing_dirty = False
                pricing_dirty = _handle_departed(
                    departed,
                    all_spots,
                    veh_stats,
                    active_driving,
                    current_time,
                    edge_data,
                    graph,
                ) or pricing_dirty

            # 行驶中车辆处理
            sub_results = traci.vehicle.getAllSubscriptionResults()
            c, t = _process_driving(
                active_driving, veh_stats, sub_results, current_time, cursor, conn, gui
            )
            completed += c
            teleported += t

            # 监控面板刷新
            if int(current_time) % PLOTTER_UPDATE_INTERVAL == 0:
                plotter.send_data(int(current_time), veh_stats)

            # 提前完赛检测
            if (completed + teleported) == TOTAL_VEHICLES_TARGET:
                h, m = int(current_time // 3600), int((current_time % 3600) // 60)
                s = int(current_time % 60)
                print(f"\n{'✨' * 30}")
                print("🎉 提前完赛！系统已达到 100% 处理率。")
                print(f"⏱️ 全局时间：{h}h{m}m{s}s ({current_time:.0f}s)")
                print(f"{'✨' * 30}\n")
                break

            # 定期同步数据库
            if int(current_time) % DB_SYNC_INTERVAL == 0 and current_time > 0:
                if pricing_dirty:
                    _compute_pricing(all_spots, pricing_index)
                    pricing_dirty = False
                sync_spots_priced(cursor, conn, all_spots)

        # 收尾
        print("💾 同步最终车位预订与价格状态...")
        if pricing_dirty:
            _compute_pricing(all_spots, pricing_index)
        sync_spots_priced(cursor, conn, all_spots)
        log_run_summary(
            cursor,
            conn,
            SCENARIO_B_NAME,
            current_time,
            TOTAL_VEHICLES_TARGET,
            completed,
            max(0, TOTAL_VEHICLES_TARGET - completed),
        )
        print(f"🏁 场景 B 结束。t={current_time:.0f}s 完成={completed} 丢失={teleported}")
    finally:
        if recorder is not None:
            recorder.stop()
        for obj in (traci, plotter, cursor, conn):
            try:
                obj.close()
            except Exception:
                pass


if __name__ == "__main__":
    run_smart_booking_with_pricing()
