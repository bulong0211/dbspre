import math
import os
import random
import sys
import time
from pathlib import Path

import traci
import traci.constants as tc
import traci.exceptions
from connection import get_db_connection
from reset_db import reset_database

# -----------------------------------------------------------------------------
# 环境配置与依赖设置
# -----------------------------------------------------------------------------
if "SUMO_HOME" in os.environ:
    sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))
else:
    sys.exit("❌ 请声明环境变量 'SUMO_HOME'")

from sumolib import checkBinary

# 配置文件路径和 SUMO 启动参数
CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"
HAS_GUI = True
sumoBinary = checkBinary("sumo-gui") if HAS_GUI else checkBinary("sumo")
sumoCmd = [sumoBinary, "-c", str(CONFIG_DIR / "demo.sumocfg")]


def run_smart_booking_with_pricing():
    """
    运行智能预订与动态定价场景的仿真。
    管理与数据库的交互、车位定价计算和基于成本优化的车辆泊位分配。
    """
    print("🔄 准备仿真环境...")
    reset_database(clear_logs=False)

    print("🔌 正在连接数据库...")
    conn = get_db_connection()  # type: ignore
    cursor = conn.cursor()

    # 从数据库查询所有停车场并构建缓存字典
    cursor.execute(
        "SELECT spot_id, edge_id, capacity, base_price, current_price FROM Parking_Spots"
    )
    all_spots = {
        row[0]: {
            "edge": row[1],
            "capacity": row[2],
            "booked": 0,
            "base_price": float(row[3]),
            "current_price": float(row[4]),
            "pos": None,
        }
        for row in cursor.fetchall()
    }

    print("🚀 启动场景 B (动态定价 + 智能预订模式) - 最大限时 2 小时...")
    traci.start(sumoCmd)

    # 获取所有停车位所在的物理坐标，用于后续距离计算
    for sid, data in all_spots.items():
        try:
            data["pos"] = traci.lane.getShape(f"{data['edge']}_0")[0]
        except traci.exceptions.TraCIException:
            data["pos"] = (0, 0)

    # 全局跟踪及统计变量
    current_protagonist = None
    total_tracked = 0

    veh_stats = {}

    completed_vehicles = 0
    teleported_vehicles = 0
    TOTAL_VEHICLES = 2500

    current_time = 0
    last_track_time = 0.0

    # 距离和价格的权重系数
    WEIGHT_DISTANCE = 1.0
    WEIGHT_PRICE = 100.0

    # -------------------------------------------------------------------------
    # 主仿真循环，时限设定为 7200 秒
    # -------------------------------------------------------------------------
    while traci.simulation.getMinExpectedNumber() > 0 and current_time <= 7200:  # type: ignore
        traci.simulationStep()
        current_time = traci.simulation.getTime()
        active_vehicles = traci.vehicle.getIDList()

        # GUI 环境下聚焦追踪车辆
        if HAS_GUI:
            if (
                current_protagonist is None
                or current_protagonist not in active_vehicles
            ):
                if len(active_vehicles) > 50:
                    struggling_candidates = [
                        v
                        for v in active_vehicles
                        if v in veh_stats and veh_stats[v].get("status") in ["driving"]
                    ]

                    if struggling_candidates:
                        current_protagonist = random.choice(struggling_candidates)
                        total_tracked += 1

                        msg = "\n" + "=" * 60
                        msg += f"🎬 [镜头切角] 锁定第 {total_tracked} 位司机: {current_protagonist} 的寻车之旅"
                        msg += "=" * 60
                        traci.simulation.writeMessage(msg)

                        try:
                            traci.gui.trackVehicle("View #0", current_protagonist)
                            traci.gui.setZoom("View #0", 2000)
                            last_track_time = time.time()
                        except Exception:
                            pass
                    else:
                        try:
                            traci.gui.trackVehicle("View #0", "")
                            traci.gui.setZoom("View #0", 250)
                        except Exception:
                            pass
            else:
                try:
                    tracked = traci.gui.getTrackedVehicle("View #0")
                    if tracked == "":
                        if time.time() - last_track_time > 8.0:
                            traci.gui.trackVehicle("View #0", current_protagonist)
                            traci.gui.setZoom("View #0", 2000)
                            last_track_time = time.time()
                    else:
                        last_track_time = time.time()
                except Exception:
                    pass

        departed = traci.simulation.getDepartedIDList()
        if departed:
            # -----------------------------------------------------------------
            # 浪涌定价机制计算
            # -----------------------------------------------------------------
            STREET_SPOT_THRESHOLD = 3
            street_stats = {}

            # 按街道维度聚合小容量路边停车位的使用情况
            for sid, data in all_spots.items():
                if data["capacity"] <= STREET_SPOT_THRESHOLD:
                    eid = data["edge"]
                    if eid not in street_stats:
                        street_stats[eid] = {"total_capacity": 0, "total_booked": 0}
                    street_stats[eid]["total_capacity"] += data["capacity"]
                    street_stats[eid]["total_booked"] += data["booked"]

            # 依据不同的车位类型计算占用率并实施阶梯式涨价
            for sid, data in all_spots.items():
                if data["capacity"] > STREET_SPOT_THRESHOLD:
                    occupancy_rate = data["booked"] / data["capacity"]
                else:
                    eid = data["edge"]
                    occupancy_rate = (
                        street_stats[eid]["total_booked"]
                        / street_stats[eid]["total_capacity"]
                    )

                if occupancy_rate > 0.90:
                    data["current_price"] = data["base_price"] * 2.0
                elif occupancy_rate > 0.70:
                    data["current_price"] = data["base_price"] * 1.5
                else:
                    data["current_price"] = data["base_price"]

            # -----------------------------------------------------------------
            # 车辆目标分配模块
            # -----------------------------------------------------------------
            for vid in departed:
                try:
                    traci.vehicle.setShapeClass(vid, "passenger")
                    spawn_pos = traci.vehicle.getPosition(vid)

                    available_spots = [
                        sid
                        for sid, data in all_spots.items()
                        if data["booked"] < data["capacity"]
                    ]

                    if not available_spots:
                        msg = f"⚠️ [系统爆满] 车辆 {vid} 无法分配到车位！"
                        traci.simulation.writeMessage(msg)
                        continue

                    best_spot = None
                    min_cost = float("inf")

                    # 基于距离惩罚和价格惩罚进行最优解筛选
                    for sid in available_spots:
                        spot_data = all_spots[sid]
                        dist = math.hypot(
                            spawn_pos[0] - spot_data["pos"][0],
                            spawn_pos[1] - spot_data["pos"][1],
                        )
                        cost = (dist * WEIGHT_DISTANCE) + (
                            spot_data["current_price"] * WEIGHT_PRICE
                        )

                        if cost < min_cost:
                            min_cost = cost
                            best_spot = sid

                    # 选定车位并更新占用和路由规划
                    all_spots[best_spot]["booked"] += 1
                    edge_id = all_spots[best_spot]["edge"]

                    traci.vehicle.changeTarget(vid, edge_id)
                    traci.vehicle.setParkingAreaStop(vid, best_spot, duration=360000.0)
                    traci.vehicle.subscribe(
                        vid, [tc.VAR_FUELCONSUMPTION, tc.VAR_DISTANCE]
                    )

                    veh_stats[vid] = {
                        "status": "driving",
                        "target_spot": best_spot,
                        "spawn_time": current_time,
                        "total_fuel": 0.0,
                        "last_dist": 0.0,
                    }
                except traci.exceptions.TraCIException:
                    pass

        sub_results = traci.vehicle.getAllSubscriptionResults()

        # ---------------------------------------------------------------------
        # 车辆行驶状态检测及数据持久化
        # ---------------------------------------------------------------------
        for vid, stats in list(veh_stats.items()):
            if stats["status"] == "driving":
                # 识别因未完成目标而从网络中消失的车辆
                if vid not in sub_results:
                    stats["status"] = "teleported"
                    teleported_vehicles += 1

                    search_time = current_time - stats["spawn_time"]
                    last_dist = stats.get("last_dist", 0.0)
                    total_fuel = stats.get("total_fuel", 0.0)

                    cruise_dist = (
                        last_dist - stats["cruise_start_dist"]
                        if stats.get("cruise_start_dist")
                        else 0
                    )

                    cursor.execute(
                        """INSERT INTO Cruising_Logs 
                           (vehicle_id, scenario, search_time_sec, cruising_distance_m, total_fuel_mg, final_spot_id) 
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (
                            vid,
                            "Smart_Booking_Priced",
                            search_time,
                            cruise_dist,
                            total_fuel,
                            None,
                        ),
                    )
                    conn.commit()

                    continue

                # 读取并累计车辆在当前时间步的指标数据
                data = sub_results[vid]
                current_fuel = data[tc.VAR_FUELCONSUMPTION]
                current_dist = data[tc.VAR_DISTANCE]

                stats["last_dist"] = current_dist
                stats["total_fuel"] = stats.get("total_fuel", 0.0) + current_fuel

                try:
                    # 判断车辆是否已在目标车位停止并进行结算
                    if traci.vehicle.isStoppedParking(vid):
                        target_spot = stats["target_spot"]
                        stats["status"] = "parked"

                        search_time = current_time - stats["spawn_time"]
                        total_fuel = stats.get("total_fuel", 0.0)

                        # 如果当前车辆是被重点追踪的主角，则打印最终历程报告
                        if vid == current_protagonist:
                            msg = f"🎉 [停车报告出炉] 司机 {current_protagonist} 停好了！\n"
                            msg += f"   ✅ 最终落脚点: {target_spot}"
                            traci.simulation.writeMessage(msg)
                            current_protagonist = None

                        cursor.execute(
                            """INSERT INTO Cruising_Logs 
                               (vehicle_id, scenario, search_time_sec, cruising_distance_m, total_fuel_mg, final_spot_id) 
                               VALUES (%s, %s, %s, %s, %s, %s)""",
                            (
                                vid,
                                "Smart_Booking_Priced",
                                search_time,
                                0,
                                total_fuel,
                                target_spot,
                            ),
                        )
                        conn.commit()
                        completed_vehicles += 1
                except traci.exceptions.TraCIException:
                    pass

        # 验证结束条件：全量车辆处理完毕
        if (completed_vehicles + teleported_vehicles) == TOTAL_VEHICLES:
            h = int(current_time // 3600)  # type: ignore
            m = int((current_time % 3600) // 60)  # type: ignore
            s = int(current_time % 60)  # type: ignore

            print("\n" + "✨" * 30)
            print("🎉 提前完赛！系统已达到 100% 处理率。")
            print(
                f"⏱️ 最后一辆车完成状态变更的全局时间为：{h} 小时 {m} 分 {s} 秒 ({current_time} 秒)"
            )
            print("✨" * 30 + "\n")
            break

        # 每隔 60 秒刷新数据库状态同步信息
        if current_time % 60 == 0:  # type: ignore
            sync_data = [
                (d["booked"], d["current_price"], sid) for sid, d in all_spots.items()
            ]
            cursor.executemany(
                "UPDATE Parking_Spots SET occupied = %s, current_price = %s WHERE spot_id = %s",
                sync_data,
            )
            conn.commit()

    # -------------------------------------------------------------------------
    # 仿真收尾与资源释放
    # -------------------------------------------------------------------------
    print("💾 正在将最终的车位预订状态与浪涌价格同步至数据库...")
    sync_data = [(d["booked"], d["current_price"], sid) for sid, d in all_spots.items()]
    cursor.executemany(
        "UPDATE Parking_Spots SET occupied = %s, current_price = %s WHERE spot_id = %s",
        sync_data,
    )
    conn.commit()
    print(
        f"🏁 场景 B (定价版) 仿真结束。当前时间步: {current_time}。共记录 {completed_vehicles} 辆车。"
    )
    traci.close()
    cursor.close()
    conn.close()


if __name__ == "__main__":
    run_smart_booking_with_pricing()
