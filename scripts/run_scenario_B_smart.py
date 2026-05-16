"""场景 B —— 智能预订 + 动态定价模式。"""

import math

import traci
import traci.constants as tc
import traci.exceptions
from core.config import (
    DB_SYNC_INTERVAL,
    ENABLE_SCREEN_RECORDING,
    PLOTTER_UPDATE_INTERVAL,
    SCENARIO_B_NAME,
    SIMULATION_DURATION_LIMIT,
    STREET_SPOT_THRESHOLD,
    TOTAL_VEHICLES_TARGET,
    WEIGHT_DISTANCE,
    WEIGHT_PRICE,
    sumoCmd,
)
from core.connection import get_db_connection
from core.db_ops import log_cruise, log_run_summary, sync_spots_priced
from core.gui_tracker import GUITracker
from core.monitor import MultiprocessingPlotter
from core.recording import prepare_visual_session
from core.reset_db import reset_database


# ---------------------------------------------------------------------------
# 静态数据加载
# ---------------------------------------------------------------------------
def _load_spots(cursor):
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
        }
    return spots


def _compute_positions(all_spots):
    """获取所有停车位的物理坐标（需在 traci.start 之后调用）。"""
    for data in all_spots.values():
        try:
            data["pos"] = traci.lane.getShape(f"{data['edge']}_0")[0]
        except traci.exceptions.TraCIException:
            data["pos"] = (0, 0)


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
def _find_best_spot(vehicle_pos, all_spots):
    """基于距离+价格综合成本选择最优车位。"""
    available = [sid for sid, d in all_spots.items() if d["booked"] < d["capacity"]]
    if not available:
        return None

    best = None
    min_cost = float("inf")
    for sid in available:
        sp = all_spots[sid]
        dist = math.hypot(vehicle_pos[0] - sp["pos"][0], vehicle_pos[1] - sp["pos"][1])
        cost = (dist * WEIGHT_DISTANCE) + (sp["current_price"] * WEIGHT_PRICE)
        if cost < min_cost:
            min_cost = cost
            best = sid
    return best


def _assign_vehicle(vid, spot_id, all_spots, veh_stats, current_time):
    """将车辆分配至指定车位并初始化追踪状态。"""
    edge_id = all_spots[spot_id]["edge"]

    traci.vehicle.changeTarget(vid, edge_id)
    traci.vehicle.setParkingAreaStop(vid, spot_id, duration=360000.0)
    traci.vehicle.subscribe(
        vid, [tc.VAR_FUELCONSUMPTION, tc.VAR_DISTANCE, tc.VAR_SPEED]
    )

    # 所有 TraCI 调用成功后才更新预订计数
    all_spots[spot_id]["booked"] += 1

    veh_stats[vid] = {
        "status": "driving",
        "target_spot": spot_id,
        "spawn_time": current_time,
        "search_time": 0.0,
        "total_fuel": 0.0,
        "last_dist": 0.0,
        "speed": 0.0,
    }


# ---------------------------------------------------------------------------
# 车辆处理
# ---------------------------------------------------------------------------
def _settle(vid, stats, current_time, spot_id, cursor, conn):
    """结算车辆行驶日志。"""
    stats["search_time"] = current_time - stats["spawn_time"]
    log_cruise(
        cursor,
        vid,
        SCENARIO_B_NAME,
        stats["search_time"],
        0,  # 场景B为预订模式，不存在巡航绕圈行为
        stats.get("total_fuel", 0.0),
        spot_id,
    )
    conn.commit()


def _handle_departed(departed, all_spots, veh_stats, active_driving, current_time):
    """新生成车辆：分配车位 → 初始化状态。"""
    booked_any = False

    for vid in departed:
        try:
            traci.vehicle.setShapeClass(vid, "passenger")
            spawn_pos = traci.vehicle.getPosition(vid)
        except traci.exceptions.TraCIException:
            continue

        spot_id = _find_best_spot(spawn_pos, all_spots)
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
        stats["total_fuel"] += data[tc.VAR_FUELCONSUMPTION]
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
    print("🔄 准备仿真环境...")
    reset_database(clear_logs=False, scenario_to_clear=SCENARIO_B_NAME)

    print("🔌 正在连接数据库...")
    conn = get_db_connection()
    cursor = conn.cursor()

    all_spots = _load_spots(cursor)
    pricing_index = _build_pricing_index(all_spots)

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
            and current_time <= SIMULATION_DURATION_LIMIT
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
                    departed, all_spots, veh_stats, active_driving, current_time
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
        total_processed = completed + teleported
        log_run_summary(
            cursor,
            conn,
            SCENARIO_B_NAME,
            current_time,
            total_processed,
            completed,
            teleported,
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
