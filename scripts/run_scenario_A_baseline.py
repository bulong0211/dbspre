import os
import random
import sys
from pathlib import Path

import traci
import traci.constants as tc
import traci.exceptions

from src.dbspre.database import get_db_connection

# -----------------------------------------------------------------------------
# 环境配置与依赖设置
# -----------------------------------------------------------------------------
if "SUMO_HOME" in os.environ:
    sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))
else:
    sys.exit("❌ 请声明环境变量 'SUMO_HOME'")

# 配置文件路径和 SUMO 启动参数
CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"
sumoCmd = [
    "sumo-gui",
    "-n",
    str(CONFIG_DIR / "optimal_cbd.net.xml"),
    "-a",
    str(CONFIG_DIR / "parking.add.xml"),
    "-r",
    str(CONFIG_DIR / "demo.rou.xml"),
    "--start",
    "--delay",
    "10",
]

HAS_GUI = "sumo-gui" in sumoCmd[0]


def run_baseline():
    """
    运行无预订模式（基线场景 A）的停车仿真。
    车辆在路网中盲目寻找可用车位，记录寻找过程中的巡航时间及燃油消耗。
    """
    print("🔌 正在连接数据库...")
    conn = get_db_connection()
    cursor = conn.cursor()

    # 从数据库初始化停车场状态，默认均为未占用状态
    cursor.execute("SELECT spot_id, edge_id, capacity FROM Parking_Spots")
    all_spots = {
        row[0]: {"edge": row[1], "capacity": row[2], "occupied": 0}
        for row in cursor.fetchall()
    }
    spot_ids = list(all_spots.keys())

    print("🚀 启动场景 A (无预订的盲目寻找模式) - 最大限时 2 小时...")
    traci.start(sumoCmd)

    # 全局跟踪及统计变量
    current_protagonist = None
    total_tracked = 0
    protagonist_search_history = []

    veh_stats = {}
    fuel_tracker = {}
    dist_tracker = {}

    completed_vehicles = 0
    teleported_vehicles = 0
    TOTAL_VEHICLES = 2500

    current_time = 0

    # -------------------------------------------------------------------------
    # 主仿真循环，时限设定为 7200 秒
    # -------------------------------------------------------------------------
    while traci.simulation.getMinExpectedNumber() > 0 and current_time <= 7200:  # type: ignore
        traci.simulationStep()
        current_time = traci.simulation.getTime()
        active_vehicles = traci.vehicle.getIDList()

        # 根据车辆速度动态调整车辆颜色以指示其行驶状态
        for vid in active_vehicles:
            try:
                if vid in veh_stats and veh_stats[vid].get("status") in [
                    "driving",
                    "cruising",
                ]:
                    speed = traci.vehicle.getSpeed(vid)

                    if speed < 0.5:  # type: ignore
                        traci.vehicle.setColor(vid, (255, 50, 50, 255))
                    else:
                        traci.vehicle.setColor(vid, (50, 200, 255, 255))

            except Exception:
                pass

        # GUI 环境下聚焦追踪受困车辆（巡航中）
        if HAS_GUI:
            if (
                current_protagonist is None
                or current_protagonist not in active_vehicles
            ):
                if len(active_vehicles) > 50:
                    struggling_candidates = [
                        v
                        for v in active_vehicles
                        if v in veh_stats
                        and veh_stats[v].get("status") in ["driving", "cruising"]
                    ]

                    if struggling_candidates:
                        current_protagonist = random.choice(struggling_candidates)
                        total_tracked += 1
                        protagonist_search_history = []

                        print("\n" + "=" * 60)
                        print(
                            f"🎬 [镜头切角] 锁定第 {total_tracked} 位司机: {current_protagonist} 的寻车之旅"
                        )
                        print("=" * 60)

                        try:
                            traci.gui.trackVehicle("View #0", current_protagonist)
                            traci.gui.setZoom("View #0", 800)
                        except Exception:
                            pass
                    else:
                        try:
                            traci.gui.trackVehicle("View #0", "")
                            traci.gui.setZoom("View #0", 250)
                        except Exception:
                            pass

        # ---------------------------------------------------------------------
        # 新生成车辆的处理及初始车位分配
        # ---------------------------------------------------------------------
        for vid in traci.simulation.getDepartedIDList():
            # 按照车位容量的比例随机分配初始目标
            weights = [all_spots[sid]["capacity"] for sid in spot_ids]
            initial_spot = random.choices(spot_ids, weights=weights, k=1)[0]
            edge_id = all_spots[initial_spot]["edge"]
            try:
                traci.vehicle.setShapeClass(vid, "passenger")
                traci.vehicle.changeTarget(vid, edge_id)
                traci.vehicle.setParkingAreaStop(vid, initial_spot, duration=360000)

                traci.vehicle.subscribe(
                    vid, [tc.VAR_FUELCONSUMPTION, tc.VAR_DISTANCE, tc.VAR_ROAD_ID]
                )

                veh_stats[vid] = {
                    "status": "driving",
                    "target_spot": initial_spot,
                    "spawn_time": current_time,
                    "cruise_start_dist": None,
                    "failed_targets": set(),
                }
            except traci.exceptions.TraCIException:
                pass

        sub_results = traci.vehicle.getAllSubscriptionResults()

        # ---------------------------------------------------------------------
        # 车辆行驶状态检测及重新规划模块
        # ---------------------------------------------------------------------
        for vid, stats in list(veh_stats.items()):
            if stats["status"] in ["driving", "cruising"]:
                # 处理因超时或其他原因被路网清除的车辆
                if vid not in sub_results:
                    stats["status"] = "teleported"
                    teleported_vehicles += 1

                    search_time = current_time - stats["spawn_time"]
                    last_dist = dist_tracker.get(vid, 0)
                    total_fuel = fuel_tracker.get(vid, 0)

                    cruise_dist = (
                        last_dist - stats["cruise_start_dist"]
                        if stats["cruise_start_dist"]
                        else 0
                    )

                    cursor.execute(
                        """INSERT INTO Cruising_Logs 
                           (vehicle_id, scenario, search_time_sec, cruising_distance_m, total_fuel_mg, final_spot_id) 
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (
                            vid,
                            "Baseline",
                            search_time,
                            cruise_dist,
                            total_fuel,
                            None,
                        ),
                    )
                    conn.commit()
                    continue

                data = sub_results[vid]
                current_fuel = data[tc.VAR_FUELCONSUMPTION]
                current_dist = data[tc.VAR_DISTANCE]
                current_edge = data[tc.VAR_ROAD_ID]

                dist_tracker[vid] = current_dist

                if vid not in fuel_tracker:
                    fuel_tracker[vid] = 0
                fuel_tracker[vid] += current_fuel

                try:
                    # 识别成功泊入的车辆并上报数据
                    if traci.vehicle.isStoppedParking(vid):
                        target_spot = stats["target_spot"]
                        all_spots[target_spot]["occupied"] += 1
                        stats["status"] = "parked"

                        search_time = current_time - stats["spawn_time"]
                        cruise_dist = (
                            current_dist - stats["cruise_start_dist"]
                            if stats["cruise_start_dist"]
                            else 0
                        )
                        total_fuel = fuel_tracker.get(vid, 0)

                        # 如果当前车辆是被重点追踪的主角，则打印最终历程报告
                        if vid == current_protagonist:
                            final_spot = target_spot
                            total_attempts = len(protagonist_search_history) + 1

                            print(
                                f"\n🎉 [追踪报告出炉] 司机 {current_protagonist} 终于停好了！"
                            )
                            print(f"   📊 寻位总次数: {total_attempts} 次")

                            if protagonist_search_history:
                                history_str = " -> ".join(protagonist_search_history)
                                print(f"   🛣️ 失败的冤枉路: {history_str}")

                            print(f"   ✅ 最终落脚点: {final_spot}")
                            print("-" * 60 + "\n")
                            current_protagonist = None

                        traci.vehicle.setColor(vid, (0, 0, 0, 255))

                        cursor.execute(
                            """INSERT INTO Cruising_Logs 
                               (vehicle_id, scenario, search_time_sec, cruising_distance_m, total_fuel_mg, final_spot_id) 
                               VALUES (%s, %s, %s, %s, %s, %s)""",
                            (
                                vid,
                                "Baseline",
                                search_time,
                                cruise_dist,
                                total_fuel,
                                target_spot,
                            ),
                        )
                        conn.commit()

                        completed_vehicles += 1
                        continue

                    # 处理已抵达目的地但车位已满的情况（盲目寻找的核心逻辑）
                    target_spot = stats["target_spot"]
                    target_edge = all_spots[target_spot]["edge"]

                    if current_edge == target_edge:
                        if (
                            all_spots[target_spot]["occupied"]
                            >= all_spots[target_spot]["capacity"]
                        ):
                            # 切换状态并开启巡航距离统计
                            if stats["status"] == "driving":
                                stats["status"] = "cruising"
                                stats["cruise_start_dist"] = current_dist

                            if vid == current_protagonist:
                                failed_spot = target_spot
                                protagonist_search_history.append(failed_spot)

                                attempt_num = len(protagonist_search_history)
                                print(
                                    f"  ❌ [第 {attempt_num} 次失败] {vid} 到达 {failed_spot}，但车位已被抢占！"
                                )
                                traci.vehicle.setColor(
                                    current_protagonist, (255, 0, 0, 255)
                                )

                            traci.vehicle.setParkingAreaStop(
                                vid, target_spot, duration=0
                            )
                            stats["failed_targets"].add(target_spot)

                            # 随机选取尚未尝试过的新目标车位
                            candidate_spots = [
                                s for s in spot_ids if s not in stats["failed_targets"]
                            ]
                            if not candidate_spots:
                                stats["failed_targets"].clear()
                                candidate_spots = spot_ids

                            candidate_weights = [
                                all_spots[s]["capacity"] for s in candidate_spots
                            ]
                            new_spot = random.choices(
                                candidate_spots, weights=candidate_weights, k=1
                            )[0]

                            stats["target_spot"] = new_spot

                            traci.vehicle.changeTarget(vid, all_spots[new_spot]["edge"])
                            traci.vehicle.setParkingAreaStop(
                                vid, new_spot, duration=360000
                            )

                            traci.vehicle.rerouteTraveltime(vid)

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
        if current_time % 60 == 0:
            veh_stats = {
                k: v
                for k, v in veh_stats.items()
                if v["status"] not in ["parked", "teleported"]
            }

            sync_data = [(d["occupied"], sid) for sid, d in all_spots.items()]
            cursor.executemany(
                "UPDATE Parking_Spots SET occupied = %s WHERE spot_id = %s",
                sync_data,
            )
            conn.commit()

    # -------------------------------------------------------------------------
    # 仿真收尾与资源释放
    # -------------------------------------------------------------------------
    print("💾 正在将最终的车位物理占用状态同步至数据库...")
    sync_data = [(d["occupied"], sid) for sid, d in all_spots.items()]
    cursor.executemany(
        "UPDATE Parking_Spots SET occupied = %s WHERE spot_id = %s",
        sync_data,
    )
    conn.commit()

    # 对仿真结束时仍未停妥的车辆进行最终结算
    if current_time >= 7200:
        print("⏳ 仿真时间达到上限，正在结算仍在路网中游荡的车辆数据...")
        for vid, stats in veh_stats.items():
            if stats["status"] in ["driving", "cruising"]:
                search_time = current_time - stats["spawn_time"]
                cruise_dist = (
                    traci.vehicle.getDistance(vid) - stats["cruise_start_dist"]
                    if stats["cruise_start_dist"]
                    else 0
                )
                total_fuel = fuel_tracker.get(vid, 0)

                cursor.execute(
                    """INSERT INTO Cruising_Logs 
                    (vehicle_id, scenario, search_time_sec, cruising_distance_m, total_fuel_mg, final_spot_id) 
                    VALUES (%s, %s, %s, %s, %s, %s)""",
                    (vid, "Baseline", search_time, cruise_dist, total_fuel, None),
                )
        conn.commit()

    print(
        f"🏁 场景 A 仿真结束。当前时间步: {current_time}。共成功记录 {completed_vehicles} 辆车的数据。"
    )
    traci.close()
    cursor.close()
    conn.close()


if __name__ == "__main__":
    run_baseline()
