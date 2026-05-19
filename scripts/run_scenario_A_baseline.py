"""场景 A —— 无预订盲目寻找模式（全路网巡航）。"""

import math
import xml.etree.ElementTree as ET

import traci
import traci.constants as tc
import traci.exceptions
from core.config import (
    CONFIG_DIR,
    DB_SYNC_INTERVAL,
    ENABLE_SCREEN_RECORDING,
    PARKING_SCAN_INTERVAL,
    PLOTTER_UPDATE_INTERVAL,
    ROUTE_EXHAUSTION_MARGIN,
    SCENARIO_A_NAME,
    SIMULATION_DURATION_LIMIT,
    TARGET_TIMEOUT,
    TOTAL_VEHICLES_TARGET,
    sumoCmd,
)
from core.connection import get_db_connection
from core.db_ops import log_cruise, log_run_summary, sync_spots
from core.emissions import (
    EMISSION_SUB_VARS,
    accumulate_environment,
    environment_log_values,
    init_environment_stats,
)
from core.gui_tracker import GUITracker
from core.monitor import MultiprocessingPlotter
from core.parking_logic import (
    check_pending,
    handle_occupied,
    reroute_random,
    scan_street,
    try_park,
)
from core.recording import prepare_visual_session
from core.reset_db import reset_database


# ---------------------------------------------------------------------------
# 静态数据加载
# ---------------------------------------------------------------------------
def _load_spots(cursor):
    """从数据库和 parking.add.xml 合并读取车位容量与物理位置。"""
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
    """解析 SUMO 路网，提取普通道路的端点、节点和几何长度。"""
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
                edges[eid] = {
                    "tx": tx,
                    "ty": ty,
                    "fx": fx,
                    "fy": fy,
                    "from_node": edge.attrib["from"],
                    "to_node": edge.attrib["to"],
                    "length": math.hypot(tx - fx, ty - fy),
                }
    return edges


def _build_opposite_map(all_edges):
    """建立每条道路对应的反向道路映射，用于视野和重路由过滤。"""
    opposite = {}
    for eid, e in all_edges.items():
        opposite[eid] = None
        for other_id, other in all_edges.items():
            if (
                other_id != eid
                and e["from_node"] == other["to_node"]
                and e["to_node"] == other["from_node"]
            ):
                opposite[eid] = other_id
                break
    return opposite


def _build_outgoing_map(all_edges, opposite_map):
    """建立每条道路驶出后的候选道路列表，排除掉头方向。"""
    outgoing = {}
    for eid, e in all_edges.items():
        to_node = e["to_node"]
        opp = opposite_map.get(eid)
        outgoing[eid] = [
            oid
            for oid, o in all_edges.items()
            if o["from_node"] == to_node and oid != eid and oid != opp
        ]
    return outgoing


def _spots_by_edge(all_spots):
    """按道路聚合车位，降低沿街扫描时的候选查找成本。"""
    result = {}
    for sid, s in all_spots.items():
        result.setdefault(s["edge"], []).append(sid)
    return result


# ---------------------------------------------------------------------------
# 车辆结算
# ---------------------------------------------------------------------------
def _cruising_distance(stats, current_dist):
    """计算车辆进入 cruising 后产生的真实巡航距离。"""
    cruise_start_dist = stats.get("cruise_start_dist")
    if cruise_start_dist is None:
        return 0.0
    return max(0.0, current_dist - cruise_start_dist)


def _settle(vid, stats, current_time, current_dist, spot_id, cursor, conn):
    """结算成功停车车辆并写入单车日志。"""
    search_time = current_time - stats["spawn_time"]
    stats["search_time"] = search_time
    cruise_dist = _cruising_distance(stats, current_dist)
    env = environment_log_values(stats)
    log_cruise(
        cursor,
        vid,
        SCENARIO_A_NAME,
        search_time,
        cruise_dist,
        env["total_fuel"],
        spot_id,
        env["total_co2"],
        env["total_nox"],
        env["total_pmx"],
    )
    conn.commit()


def _settle_lost(vid, stats, current_time, cursor, conn):
    """结算未能停车或已离开仿真的车辆。"""
    stats["status"] = "teleported"
    search_time = current_time - stats["spawn_time"]
    stats["search_time"] = search_time
    cruise_dist = _cruising_distance(stats, stats.get("last_dist", 0.0))
    env = environment_log_values(stats)
    log_cruise(
        cursor,
        vid,
        SCENARIO_A_NAME,
        search_time,
        cruise_dist,
        env["total_fuel"],
        None,
        env["total_co2"],
        env["total_nox"],
        env["total_pmx"],
    )
    conn.commit()


def _init_stats(current_time):
    """初始化车辆状态；出发时先处于 driving，满足条件后才进入 cruising。"""
    stats = {
        "status": "driving",
        "target_spot": None,
        "pending_spot": None,
        "pending_spot_edge": None,
        "initial_destination_pending": True,
        "spawn_time": current_time,
        "search_time": 0.0,
        "cruise_start_dist": None,
        "last_dist": 0.0,
        "speed": 0.0,
    }
    stats.update(init_environment_stats())
    return stats


def _start_cruising(stats, current_time, current_dist, reason):
    """将车辆从普通行驶切换为巡航，并记录切换时间、距离和原因。"""
    if stats.get("status") != "driving":
        return False
    stats["status"] = "cruising"
    stats["cruise_start_time"] = current_time
    stats["cruise_start_dist"] = current_dist
    stats["cruise_start_reason"] = reason
    stats["initial_destination_pending"] = False
    return True


def _record_external_cruise_start(stats, current_time, current_dist):
    """补记由停车逻辑模块触发的巡航起点。"""
    if stats.get("status") != "cruising" or "cruise_start_time" in stats:
        return
    stats["cruise_start_time"] = current_time
    stats["cruise_start_dist"] = current_dist


SUB_VARS = [
    tc.VAR_DISTANCE,
    tc.VAR_ROAD_ID,
    tc.VAR_SPEED,
    tc.VAR_POSITION,
    tc.VAR_LANEPOSITION,
    *EMISSION_SUB_VARS,
]


# ---------------------------------------------------------------------------
# 单车辆步进处理
# ---------------------------------------------------------------------------
def _process_vehicle(
    vid,
    stats,
    data,
    current_time,
    all_spots,
    spots_by_edge,
    all_edges_list,
    opposite_map,
    outgoing_map,
    edge_lengths,
    cursor,
    conn,
    gui,
):
    """推进单辆活动车辆的寻位、承诺车位、停入和失效处理。"""
    current_dist = data[tc.VAR_DISTANCE]
    current_edge = data[tc.VAR_ROAD_ID]
    current_lanepos = data.get(tc.VAR_LANEPOSITION, 0.0)

    stats["last_dist"] = current_dist
    accumulate_environment(stats, data)
    stats["speed"] = data[tc.VAR_SPEED]

    # 已成功泊入
    if traci.vehicle.isStoppedParking(vid):
        target = stats.get("target_spot")
        if target and target in all_spots:
            all_spots[target]["occupied"] += 1
        stats["status"] = "parked"
        _settle(vid, stats, current_time, current_dist, target, cursor, conn)
        if vid == gui.current_protagonist:
            elapsed = current_time - stats["spawn_time"]
            traci.simulation.writeMessage(
                f"  [{vid}] 泊入成功 {target or '?'} | "
                f"耗时 {int(elapsed // 60)}分{int(elapsed % 60)}秒 | "
                f"行驶 {current_dist:.0f}m"
            )
        gui.on_vehicle_parked(vid)
        return True

    tracked = vid == gui.current_protagonist

    # 处理延时 pending 车位
    had_pending = bool(stats.get("pending_spot"))
    pending_id = stats.get("pending_spot")
    had_target = bool(stats.get("target_spot"))
    target_id = stats.get("target_spot")
    was_driving = stats.get("status") == "driving"
    check_pending(
        vid, stats, current_edge, all_spots, all_edges_list, opposite_map, outgoing_map
    )
    _record_external_cruise_start(stats, current_time, current_dist)
    if stats.get("target_spot"):
        target_still = stats.get("target_spot")

        # 记录 target 首次锁定时间，用于超时检测
        if stats.get("_target_since") != target_still:
            stats["_target_since"] = target_still
            stats["_target_at"] = current_time

        # 超时：锁定后长时间未泊入 → 放弃
        if current_time - stats.get("_target_at", current_time) > TARGET_TIMEOUT:
            try:
                traci.vehicle.setParkingAreaStop(vid, target_still, duration=0)
            except traci.exceptions.TraCIException:
                pass
            stats["target_spot"] = None
            stats.pop("_target_since", None)
            stats.pop("_target_at", None)
            started_cruising = _start_cruising(
                stats, current_time, current_dist, "spot_timeout"
            )
            reroute_random(vid, all_edges_list, opposite_map, outgoing_map)
            if tracked:
                if started_cruising:
                    traci.simulation.writeMessage(
                        f"  [{vid}] 车位 {target_still} 等待超时，开始巡航"
                    )
                else:
                    traci.simulation.writeMessage(
                        f"  [{vid}] 车位 {target_still} 等待超时，放弃"
                    )
            return False

        handle_occupied(
            vid,
            stats,
            current_edge,
            all_spots,
            all_edges_list,
            opposite_map,
            outgoing_map,
        )
        _record_external_cruise_start(stats, current_time, current_dist)
        if tracked:
            if was_driving and stats.get("status") == "cruising":
                traci.simulation.writeMessage(
                    f"  [{vid}] 车位 {target_id} 失效，开始巡航"
                )
            elif had_target and not stats.get("target_spot"):
                traci.simulation.writeMessage(
                    f"  [{vid}] 准备停入的车位 {target_id} 失效，重新寻找"
                )
            elif had_pending and target_still == stats.get("target_spot"):
                traci.simulation.writeMessage(
                    f"  [{vid}] 到达 {pending_id} 所在道路，准备泊入"
                )
        return False

    if tracked and had_pending and not stats.get("pending_spot"):
        if was_driving and stats.get("status") == "cruising":
            traci.simulation.writeMessage(
                f"  [{vid}] 预定的车位 {pending_id} 失效，开始巡航"
            )
        else:
            traci.simulation.writeMessage(
                f"  [{vid}] 预定的车位 {pending_id} 失效，重新寻找"
            )

    # 沿街寻找空车位
    do_full = (
        int(current_time) % PARKING_SCAN_INTERVAL == 0
        or had_pending
        and not stats.get("pending_spot")
    )
    found_spot, found_edge = scan_street(
        vid,
        current_edge,
        current_lanepos,
        spots_by_edge,
        all_spots,
        opposite_map,
        outgoing_map,
        edge_lengths,
        full_scan=do_full,
    )

    if found_spot and found_spot == stats.get("pending_spot"):
        pass
    elif found_spot:
        pending_before = stats.get("pending_spot")  # check_pending 可能已清掉
        ok = try_park(vid, found_spot, found_edge, stats, current_edge, all_spots)
        if ok:
            if tracked:
                if had_pending and pending_before and not stats.get("pending_spot"):
                    traci.simulation.writeMessage(
                        f"  [{vid}] 放弃预定 {pending_id}，路边发现更近的 {found_spot}"
                    )
                elif found_edge == current_edge:
                    traci.simulation.writeMessage(
                        f"  [{vid}] 路边发现空车位 {found_spot}，正在停入"
                    )
                else:
                    traci.simulation.writeMessage(
                        f"  [{vid}] 发现空车位 {found_spot}，正在赶往"
                    )
        else:
            if tracked:
                # 分析失败原因，不刷屏
                has_commit = stats.get("target_spot") or stats.get("pending_spot")
                if has_commit:
                    pass  # 已有预定，拒绝新车位是正常行为，不输出
                elif found_edge == current_edge:
                    spot = all_spots.get(found_spot, {})
                    if spot.get("occupied", 0) >= spot.get("capacity", 1):
                        traci.simulation.writeMessage(
                            f"  [{vid}] 车位 {found_spot} 刚被占"
                        )
                    else:
                        traci.simulation.writeMessage(
                            f"  [{vid}] SUMO 拒绝停入 {found_spot}"
                        )
                else:
                    traci.simulation.writeMessage(
                        f"  [{vid}] 无法路由至 {found_spot} 所在道路"
                    )
    else:
        # 已承诺车位（pending）时跳过重路由，否则会覆盖目的地
        if not stats.get("pending_spot") and not stats.get("target_spot"):
            route = traci.vehicle.getRoute(vid)
            if traci.vehicle.getRouteIndex(vid) >= len(route) - ROUTE_EXHAUSTION_MARGIN:
                if stats.get("initial_destination_pending"):
                    _start_cruising(
                        stats, current_time, current_dist, "route_exhausted"
                    )
                    if tracked:
                        traci.simulation.writeMessage(
                            f"  [{vid}] 首次随机目的地即将到达，未发现空车位，开始巡航"
                        )
                reroute_random(vid, all_edges_list, opposite_map, outgoing_map)

    return False


# ---------------------------------------------------------------------------
# 主仿真循环
# ---------------------------------------------------------------------------
def run_baseline():
    """运行场景 A 的全路网盲目寻位仿真。"""
    print("🔄 准备仿真环境...")
    reset_database(clear_logs=True)

    print("🔌 正在连接数据库...")
    conn = get_db_connection()
    cursor = conn.cursor()

    all_edges = _load_edges()
    all_edges_list = list(all_edges.keys())
    all_spots = _load_spots(cursor)
    opposite_map = _build_opposite_map(all_edges)
    outgoing_map = _build_outgoing_map(all_edges, opposite_map)
    edge_lengths = {eid: ed["length"] for eid, ed in all_edges.items()}
    spots_by_edge = _spots_by_edge(all_spots)

    veh_stats = {}
    active_vids = set()
    completed = teleported = 0
    plotter = None
    recorder = None

    try:
        print("🚀 启动场景 A (全路网盲目寻位) — 最大限时 2 小时...")
        traci.start(sumoCmd)
        gui = GUITracker()
        plotter = MultiprocessingPlotter("场景 A — 全路网盲目寻位模式")
        recorder = prepare_visual_session(SCENARIO_A_NAME, ENABLE_SCREEN_RECORDING)

        current_time = 0
        while (
            traci.simulation.getMinExpectedNumber() > 0
            and current_time < SIMULATION_DURATION_LIMIT
        ):
            traci.simulationStep()
            current_time = traci.simulation.getTime()
            active = traci.vehicle.getIDList()

            gui.update(active, veh_stats, current_time)

            # 新车初始化
            for vid in traci.simulation.getDepartedIDList():
                try:
                    traci.vehicle.setShapeClass(vid, "passenger")
                    traci.vehicle.setSpeedFactor(vid, 0.4)
                    traci.vehicle.setImperfection(vid, 0.9)
                    traci.vehicle.subscribe(vid, SUB_VARS)
                except traci.exceptions.TraCIException:
                    continue
                veh_stats[vid] = _init_stats(current_time)
                active_vids.add(vid)
                if not reroute_random(vid, all_edges_list, opposite_map, outgoing_map):
                    _settle_lost(vid, veh_stats[vid], current_time, cursor, conn)
                    active_vids.discard(vid)
                    teleported += 1

            sub_results = traci.vehicle.getAllSubscriptionResults()

            # 行驶中车辆处理
            for vid in list(active_vids):
                stats = veh_stats.get(vid)
                if stats is None or stats["status"] not in ("driving", "cruising"):
                    active_vids.discard(vid)
                    continue
                if vid not in sub_results:
                    _settle_lost(vid, stats, current_time, cursor, conn)
                    active_vids.discard(vid)
                    teleported += 1
                    continue
                parked = _process_vehicle(
                    vid,
                    stats,
                    sub_results[vid],
                    current_time,
                    all_spots,
                    spots_by_edge,
                    all_edges_list,
                    opposite_map,
                    outgoing_map,
                    edge_lengths,
                    cursor,
                    conn,
                    gui,
                )
                if parked:
                    active_vids.discard(vid)
                    completed += 1

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
                sync_spots(cursor, conn, all_spots)

        # 收尾
        print("💾 同步最终车位状态...")
        sync_spots(cursor, conn, all_spots)

        if current_time >= SIMULATION_DURATION_LIMIT:
            print("⏳ 仿真时间达到上限，结算剩余车辆...")
            for vid in list(active_vids):
                stats = veh_stats.get(vid)
                if stats is None or stats["status"] not in ("driving", "cruising"):
                    continue
                try:
                    curr_dist = traci.vehicle.getDistance(vid)
                except traci.exceptions.TraCIException:
                    curr_dist = stats.get("last_dist", 0.0)
                _settle(vid, stats, current_time, curr_dist, None, cursor, conn)
            conn.commit()

        log_run_summary(
            cursor,
            conn,
            SCENARIO_A_NAME,
            current_time,
            TOTAL_VEHICLES_TARGET,
            completed,
            max(0, TOTAL_VEHICLES_TARGET - completed),
        )
        print(f"🏁 场景 A 结束。t={current_time:.0f}s 完成={completed} 丢失={teleported}")
    finally:
        if recorder is not None:
            recorder.stop()
        for obj in (traci, plotter, cursor, conn):
            try:
                if obj is not None:
                    obj.close()
            except Exception:
                pass


if __name__ == "__main__":
    run_baseline()
