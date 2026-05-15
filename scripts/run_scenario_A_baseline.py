"""场景 A —— 无预订盲目寻找模式（沿街张望模型）。"""
import math
import xml.etree.ElementTree as ET
import traci
import traci.constants as tc
import traci.exceptions

from config import (
    CONFIG_DIR, sumoCmd,
    SIMULATION_DURATION_LIMIT, TOTAL_VEHICLES_TARGET,
    CBD_BOUNDS, DB_SYNC_INTERVAL,
    CBD_CENTER_X, CBD_CENTER_Y,
    SEARCH_EXPAND_INTERVAL, SEARCH_EXPAND_STEP, SEARCH_EXPAND_MIN_RADIUS, SEARCH_EXPAND_LEVELS,
    ROUTE_EXHAUSTION_MARGIN, PARKING_SCAN_INTERVAL, PLOTTER_UPDATE_INTERVAL,
)
from connection import get_db_connection
from monitor import MultiprocessingPlotter
from reset_db import reset_database
from db_ops import log_cruise, sync_spots
from gui_tracker import GUITracker
from parking_logic import (
    reroute_to_cbd, scan_street, try_park, check_pending, handle_occupied,
)


# ---------------------------------------------------------------------------
# 静态数据加载
# ---------------------------------------------------------------------------
def _load_spots(cursor):
    cursor.execute("SELECT spot_id, edge_id, capacity FROM Parking_Spots")
    spots = {
        row[0]: {"edge": row[1], "capacity": row[2], "occupied": 0, "startPos": 0.0}
        for row in cursor.fetchall()
    }
    pa_tree = ET.parse(CONFIG_DIR / "parking.add.xml")
    for pa in pa_tree.getroot().findall("parkingArea"):
        sid = pa.attrib["id"]
        if sid in spots:
            spots[sid]["startPos"] = float(pa.attrib["startPos"])
            spots[sid]["lane"] = pa.attrib.get("lane", "")
    return spots


def _load_edges():
    tree = ET.parse(CONFIG_DIR / "demo.net.xml")
    nodes = {
        n.attrib["id"]: (float(n.attrib["x"]), float(n.attrib["y"]))
        for n in tree.getroot().findall("junction")
    }
    edges = {}
    for edge in tree.getroot().findall("edge"):
        if "function" not in edge.attrib:
            eid = edge.attrib["id"]
            if edge.attrib["from"] in nodes and edge.attrib["to"] in nodes:
                fx, fy = nodes[edge.attrib["from"]]
                tx, ty = nodes[edge.attrib["to"]]
                length = math.hypot(tx - fx, ty - fy)
                edges[eid] = {
                    "tx": tx, "ty": ty, "fx": fx, "fy": fy,
                    "from_node": edge.attrib["from"],
                    "to_node": edge.attrib["to"],
                    "length": length,
                }
    return edges


def _cbd_edges(edges):
    b = CBD_BOUNDS
    return [eid for eid, e in edges.items()
            if b["x_min"] <= e["tx"] <= b["x_max"] and b["y_min"] <= e["ty"] <= b["y_max"]
            and b["x_min"] <= e["fx"] <= b["x_max"] and b["y_min"] <= e["fy"] <= b["y_max"]]


def _spots_by_edge(all_spots):
    result = {}
    for sid, s in all_spots.items():
        result.setdefault(s["edge"], []).append(sid)
    return result


def _build_expansion_levels(all_edges):
    """预计算搜索范围逐级扩张的边集合。

    级别 0: CBD 核心（600m 半径）→ 级别 N: 扩张至全路网。
    返回 list[list[edge_id]]，索引 = 级别。
    """
    levels = []
    for level in range(SEARCH_EXPAND_LEVELS):
        radius = SEARCH_EXPAND_MIN_RADIUS + level * SEARCH_EXPAND_STEP
        min_x, max_x = CBD_CENTER_X - radius, CBD_CENTER_X + radius
        min_y, max_y = CBD_CENTER_Y - radius, CBD_CENTER_Y + radius
        edges = [eid for eid, e in all_edges.items()
                 if min_x <= e["tx"] <= max_x and min_y <= e["ty"] <= max_y
                 and min_x <= e["fx"] <= max_x and min_y <= e["fy"] <= max_y]
        if edges:
            levels.append(edges)
    # 最后一级：全路网
    levels.append(list(all_edges.keys()))
    return levels


def _build_opposite_map(all_edges):
    """构建 edge_id → 对向车道 edge_id 的映射。

    两条边互为对向当且仅当它们共享相同的起止节点但方向相反。
    """
    opposite = {}
    for eid, e in all_edges.items():
        opposite[eid] = None
        for other_id, other in all_edges.items():
            if other_id != eid and e["from_node"] == other["to_node"] and e["to_node"] == other["from_node"]:
                opposite[eid] = other_id
                break
    return opposite


def _build_outgoing_map(all_edges, opposite_map):
    """构建 edge_id → 交叉方向可达边列表。

    从当前边的 to_node 出发的所有边（排除自身和对向），
    模拟驾驶员在路口左右张望能看到的交叉道路。
    """
    outgoing = {}
    for eid, e in all_edges.items():
        to_node = e["to_node"]
        opp = opposite_map.get(eid)
        outgoing[eid] = [oid for oid, o in all_edges.items()
                         if o["from_node"] == to_node
                         and oid != eid
                         and oid != opp]
    return outgoing


def _target_edges_for_vehicle(stats, current_time, expansion_levels):
    """根据车辆巡航时长返回当前应使用的目标边集合。"""
    if stats["status"] == "driving":
        return expansion_levels[0]  # 未入 CBD，导向核心区
    cruise_time = current_time - stats.get("cruise_start_time", current_time)
    level = min(int(cruise_time // SEARCH_EXPAND_INTERVAL), len(expansion_levels) - 1)
    return expansion_levels[level]


SUB_VARS = [
    tc.VAR_FUELCONSUMPTION, tc.VAR_DISTANCE, tc.VAR_ROAD_ID,
    tc.VAR_SPEED, tc.VAR_POSITION, tc.VAR_LANEPOSITION,
]


# ---------------------------------------------------------------------------
# 车辆结算
# ---------------------------------------------------------------------------
def _settle(vid, stats, current_time, current_dist, spot_id, cursor, conn):
    search_time = current_time - (stats.get("cruise_start_time") or stats["spawn_time"])
    stats["search_time"] = search_time
    cruise_dist = (current_dist - stats["cruise_start_dist"]) if stats["cruise_start_dist"] else 0
    log_cruise(cursor, vid, "Baseline", search_time, cruise_dist,
               stats.get("total_fuel", 0.0), spot_id)
    conn.commit()


def _settle_lost(vid, stats, current_time, cursor, conn):
    stats["status"] = "teleported"
    search_time = current_time - stats["spawn_time"]
    stats["search_time"] = search_time
    cruise_dist = (stats.get("last_dist", 0.0) - stats["cruise_start_dist"]) if stats["cruise_start_dist"] else 0
    log_cruise(cursor, vid, "Baseline", search_time, cruise_dist,
               stats.get("total_fuel", 0.0), None)
    conn.commit()


def _init_stats(current_time):
    return {
        "status": "driving",
        "target_spot": None,
        "pending_spot": None,
        "pending_spot_edge": None,
        "spawn_time": current_time,
        "search_time": 0.0,
        "cruise_start_dist": None,
        "cruise_start_time": None,
        "total_fuel": 0.0,
        "last_dist": 0.0,
        "speed": 0.0,
    }


# ---------------------------------------------------------------------------
# 单车辆步进处理
# ---------------------------------------------------------------------------
def _process_vehicle(vid, stats, data, current_time,
                     all_spots, spots_by_edge, expansion_levels,
                     opposite_map, outgoing_map, edge_lengths,
                     cursor, conn, gui):
    current_dist = data[tc.VAR_DISTANCE]
    current_edge = data[tc.VAR_ROAD_ID]
    current_pos = data[tc.VAR_POSITION]
    current_lanepos = data.get(tc.VAR_LANEPOSITION, 0.0)

    stats["last_dist"] = current_dist
    stats["total_fuel"] = stats.get("total_fuel", 0.0) + data[tc.VAR_FUELCONSUMPTION]
    stats["speed"] = data[tc.VAR_SPEED]

    # 已成功泊入
    if traci.vehicle.isStoppedParking(vid):
        target = stats.get("target_spot")
        if target:
            all_spots[target]["occupied"] += 1
        stats["status"] = "parked"
        _settle(vid, stats, current_time, current_dist, target, cursor, conn)
        gui.on_vehicle_parked(vid)
        return

    target_edges = _target_edges_for_vehicle(stats, current_time, expansion_levels)

    # 进入 CBD → 开始巡航
    if stats["status"] == "driving":
        x, y = current_pos
        b = CBD_BOUNDS
        if b["x_min"] <= x <= b["x_max"] and b["y_min"] <= y <= b["y_max"]:
            stats["status"] = "cruising"
            stats["cruise_start_dist"] = current_dist
            stats["cruise_start_time"] = current_time
            traci.vehicle.setSpeedFactor(vid, 0.4)
            traci.vehicle.setImperfection(vid, 0.9)
            reroute_to_cbd(vid, target_edges)
            return
        # 未进入 CBD，但路由可能耗尽
        route = traci.vehicle.getRoute(vid)
        if traci.vehicle.getRouteIndex(vid) >= len(route) - ROUTE_EXHAUSTION_MARGIN:
            reroute_to_cbd(vid, target_edges)
        return

    if stats["status"] != "cruising":
        return

    # --- 巡航中 ---
    # 先处理延时 pending 车位
    check_pending(vid, stats, current_edge, current_lanepos, all_spots)
    if stats.get("target_spot"):
        handle_occupied(vid, stats, current_edge, current_lanepos, all_spots, target_edges)
        return

    # 沿街寻找空车位（极轻量：只扫当前道路 + 下一条路）
    found_spot = found_edge = None
    if int(current_time) % PARKING_SCAN_INTERVAL == 0:
        found_spot, found_edge = scan_street(
            vid, current_edge, current_lanepos, spots_by_edge, all_spots,
            opposite_map, outgoing_map, edge_lengths)

    if found_spot:
        try_park(vid, found_spot, found_edge, stats, current_edge, current_lanepos, all_spots)
    else:
        # 路由将耗尽 → 换条路继续巡航（目标边随搜索级别扩张）
        route = traci.vehicle.getRoute(vid)
        if traci.vehicle.getRouteIndex(vid) >= len(route) - ROUTE_EXHAUSTION_MARGIN:
            reroute_to_cbd(vid, target_edges)


# ---------------------------------------------------------------------------
# 主仿真循环
# ---------------------------------------------------------------------------
def run_baseline():
    print("🔄 准备仿真环境...")
    reset_database(clear_logs=True)

    print("🔌 正在连接数据库...")
    conn = get_db_connection()
    cursor = conn.cursor()

    all_edges = _load_edges()
    all_spots = _load_spots(cursor)
    cbd_edges = _cbd_edges(all_edges)
    expansion_levels = _build_expansion_levels(all_edges)
    opposite_map = _build_opposite_map(all_edges)
    outgoing_map = _build_outgoing_map(all_edges, opposite_map)
    edge_lengths = {eid: ed["length"] for eid, ed in all_edges.items()}
    spots_by_edge = _spots_by_edge(all_spots)

    gui = GUITracker()
    plotter = MultiprocessingPlotter("场景 A — 沿街盲目寻位模式")

    veh_stats = {}
    completed = teleported = 0
    TOTAL = TOTAL_VEHICLES_TARGET

    print("🚀 启动场景 A (沿街张望盲目寻位) — 最大限时 2 小时...")
    traci.start(sumoCmd)

    current_time = 0
    while (traci.simulation.getMinExpectedNumber() > 0
           and current_time <= SIMULATION_DURATION_LIMIT):
        traci.simulationStep()
        current_time = traci.simulation.getTime()
        active = traci.vehicle.getIDList()

        gui.update(active, veh_stats, current_time)

        # 新车初始化 — 重定向到 CBD 内随机边
        for vid in traci.simulation.getDepartedIDList():
            try:
                traci.vehicle.setShapeClass(vid, "passenger")
                traci.vehicle.subscribe(vid, SUB_VARS)
            except traci.exceptions.TraCIException:
                continue
            veh_stats[vid] = _init_stats(current_time)
            if not reroute_to_cbd(vid, cbd_edges):
                _settle_lost(vid, veh_stats.pop(vid), current_time, cursor, conn)
                teleported += 1

        sub_results = traci.vehicle.getAllSubscriptionResults()

        for vid, stats in list(veh_stats.items()):
            if stats["status"] not in ("driving", "cruising"):
                continue
            if vid not in sub_results:
                _settle_lost(vid, stats, current_time, cursor, conn)
                teleported += 1
                continue
            _process_vehicle(vid, stats, sub_results[vid], current_time,
                             all_spots, spots_by_edge, expansion_levels,
                             opposite_map, outgoing_map, edge_lengths,
                             cursor, conn, gui)
            if stats["status"] == "parked":
                completed += 1

        # 监控面板（降频）
        if int(current_time) % PLOTTER_UPDATE_INTERVAL == 0:
            plotter.send_data(int(current_time), veh_stats)

        if (completed + teleported) == TOTAL:
            h, m, s = int(current_time // 3600), int((current_time % 3600) // 60), int(current_time % 60)
            print(f"\n{'✨'*30}\n🎉 提前完赛！{h}h{m}m{s}s ({current_time:.0f}s)\n{'✨'*30}\n")
            break

        if int(current_time) % DB_SYNC_INTERVAL == 0 and current_time > 0:
            sync_spots(cursor, conn, all_spots)

    # 收尾
    print("💾 同步最终车位状态...")
    sync_spots(cursor, conn, all_spots)

    if current_time >= SIMULATION_DURATION_LIMIT:
        print("⏳ 仿真时间达到上限，结算剩余车辆...")
        for vid, stats in veh_stats.items():
            if stats["status"] not in ("driving", "cruising"):
                continue
            try:
                curr_dist = traci.vehicle.getDistance(vid)
            except traci.exceptions.TraCIException:
                curr_dist = stats.get("last_dist", 0.0)
            _settle(vid, stats, current_time, curr_dist, None, cursor, conn)
        conn.commit()

    print(f"🏁 场景 A 结束。t={current_time:.0f}s 完成={completed} 丢失={teleported}")
    for obj in (traci, plotter, cursor, conn):
        try:
            obj.close()
        except Exception:
            pass


if __name__ == "__main__":
    run_baseline()
