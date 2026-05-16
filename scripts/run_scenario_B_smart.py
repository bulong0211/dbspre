"""场景 B —— 智能预订 + 动态定价模式。"""

import math

import traci
import traci.constants as tc
import traci.exceptions
from core.config import (
    DB_SYNC_INTERVAL,
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
from core.db_ops import log_cruise, sync_spots_priced
from core.gui_tracker import GUITracker
from core.monitor import MultiprocessingPlotter
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
def _compute_pricing(all_spots):
    """按街道维度聚合小容量路边车位，依据占用率阶梯式涨价。"""
    street_stats = {}
    for data in all_spots.values():
        if data["capacity"] <= STREET_SPOT_THRESHOLD:
            eid = data["edge"]
            if eid not in street_stats:
                street_stats[eid] = {"total_capacity": 0, "total_booked": 0}
            street_stats[eid]["total_capacity"] += data["capacity"]
            street_stats[eid]["total_booked"] += data["booked"]

    for data in all_spots.values():
        if data["capacity"] > STREET_SPOT_THRESHOLD:
            rate = data["booked"] / data["capacity"]
        else:
            eid = data["edge"]
            rate = (
                street_stats[eid]["total_booked"] / street_stats[eid]["total_capacity"]
            )

        if rate > 0.90:
            data["current_price"] = data["base_price"] * 2.0
        elif rate > 0.70:
            data["current_price"] = data["base_price"] * 1.5
        else:
            data["current_price"] = data["base_price"]


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
        "target_at": current_time,
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


def _handle_departed(departed, all_spots, veh_stats, current_time):
    """新生成车辆：分配车位 → 初始化状态。"""
    for vid in departed:
        try:
            traci.vehicle.setShapeClass(vid, "passenger")
            traci.vehicle.setSpeedFactor(vid, 0.4)
            traci.vehicle.setImperfection(vid, 0.9)
            spawn_pos = traci.vehicle.getPosition(vid)
        except traci.exceptions.TraCIException:
            continue

        spot_id = _find_best_spot(spawn_pos, all_spots)
        if spot_id is None:
            traci.simulation.writeMessage(f"⚠️ [系统爆满] 车辆 {vid} 无法分配到车位！")
            continue

        try:
            _assign_vehicle(vid, spot_id, all_spots, veh_stats, current_time)
        except traci.exceptions.TraCIException:
            traci.simulation.writeMessage(
                f"⚠️ [分配失败] 车辆 {vid} 路由至 {spot_id} 失败"
            )


def _process_driving(veh_stats, sub_results, current_time, active, all_spots, cursor, conn, gui):
    """行驶中车辆：指标更新、消失检测、泊车结算。"""
    completed = 0
    teleported = 0

    for vid, stats in list(veh_stats.items()):
        if stats["status"] != "driving":
            continue

        # 基于活跃列表判断车辆是否从路网中消失
        if vid not in active:
            old_target = stats["target_spot"]
            if old_target and old_target in all_spots:
                all_spots[old_target]["booked"] = max(
                    0, all_spots[old_target]["booked"] - 1
                )
            stats["status"] = "teleported"
            teleported += 1
            _settle(vid, stats, current_time, None, cursor, conn)
            continue

        # 订阅缺失：可能刚停好导致 SUMO 取消了订阅，先确认
        if vid not in sub_results:
            try:
                if traci.vehicle.isStoppedParking(vid):
                    target = stats["target_spot"]
                    stats["status"] = "parked"
                    _settle(vid, stats, current_time, target, cursor, conn)
                    if gui and vid == gui.current_protagonist:
                        traci.simulation.writeMessage(
                            f"🎉 [停车报告出炉] 司机 {vid} 停好了！\n"
                            f"   ✅ 最终落脚点: {target}"
                        )
                        gui.on_vehicle_parked(vid)
                    completed += 1
            except traci.exceptions.TraCIException:
                pass
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
                _settle(vid, stats, current_time, target, cursor, conn)

                if gui and vid == gui.current_protagonist:
                    traci.simulation.writeMessage(
                        f"🎉 [停车报告出炉] 司机 {vid} 停好了！\n"
                        f"   ✅ 最终落脚点: {target}"
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

    print("🚀 启动场景 B (动态定价 + 智能预订模式) - 最大限时 2 小时...")
    traci.start(sumoCmd)
    _compute_positions(all_spots)

    gui = GUITracker()
    plotter = MultiprocessingPlotter("场景 B - 智能预订监控面板", layout="B")

    veh_stats = {}
    completed = 0
    teleported = 0
    current_time = 0

    while (
        traci.simulation.getMinExpectedNumber() > 0
        and current_time <= SIMULATION_DURATION_LIMIT
    ):
        traci.simulationStep()
        current_time = traci.simulation.getTime()
        active = traci.vehicle.getIDList()

        gui.update(active, veh_stats, current_time)

        # 每步更新浪涌定价
        _compute_pricing(all_spots)

        # 新车初始化
        departed = traci.simulation.getDepartedIDList()
        if departed:
            _handle_departed(departed, all_spots, veh_stats, current_time)

        # 行驶中车辆处理
        sub_results = traci.vehicle.getAllSubscriptionResults()
        c, t = _process_driving(
            veh_stats, sub_results, current_time, active, all_spots, cursor, conn, gui
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
            sync_spots_priced(cursor, conn, all_spots)

    # 收尾
    print("💾 同步最终车位预订与价格状态...")
    sync_spots_priced(cursor, conn, all_spots)
    print(f"🏁 场景 B 结束。t={current_time:.0f}s 完成={completed} 丢失={teleported}")

    for obj in (traci, plotter, cursor, conn):
        try:
            obj.close()
        except Exception:
            pass


if __name__ == "__main__":
    run_smart_booking_with_pricing()
