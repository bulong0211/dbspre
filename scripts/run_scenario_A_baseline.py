import os
import random
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import traci
import traci.constants as tc
import traci.exceptions
from connection import get_db_connection
from monitor import MultiprocessingPlotter
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


def run_baseline():
    """
    运行无预订模式（基线场景 A）的停车仿真。
    车辆在路网中盲目寻找可用车位，记录寻找过程中的巡航时间及燃油消耗。
    """
    print("🔄 准备仿真环境...")
    reset_database(clear_logs=True)

    print("🔌 正在连接数据库...")
    conn = get_db_connection()
    cursor = conn.cursor()

    # 从数据库查询所有停车场并构建缓存字典
    cursor.execute("SELECT spot_id, edge_id, capacity FROM Parking_Spots")
    all_spots = {
        row[0]: {"edge": row[1], "capacity": row[2], "occupied": 0, "startPos": 0.0}
        for row in cursor.fetchall()
    }

    # 读取车位物理位置信息
    pa_tree = ET.parse(CONFIG_DIR / "parking.add.xml")
    for pa in pa_tree.getroot().findall("parkingArea"):
        sid = pa.attrib["id"]
        if sid in all_spots:
            all_spots[sid]["startPos"] = float(pa.attrib["startPos"])

    # 提前解析路网，用于动态扩张搜索半径和识别CBD
    tree = ET.parse(CONFIG_DIR / "demo.net.xml")
    nodes = {
        n.attrib["id"]: (float(n.attrib["x"]), float(n.attrib["y"]))
        for n in tree.getroot().findall("junction")
    }
    all_edge_data = {}
    for edge in tree.getroot().findall("edge"):
        if "function" not in edge.attrib:
            eid = edge.attrib["id"]
            if edge.attrib["from"] in nodes and edge.attrib["to"] in nodes:
                fx, fy = nodes[edge.attrib["from"]]
                tx, ty = nodes[edge.attrib["to"]]
                all_edge_data[eid] = {"tx": tx, "ty": ty, "fx": fx, "fy": fy}

    spots_by_edge = {}
    for sid, sdata in all_spots.items():
        spots_by_edge.setdefault(sdata["edge"], []).append(sid)

    print("🚀 启动场景 A (无预订的盲目寻找模式) - 最大限时 2 小时...")
    traci.start(sumoCmd)

    # 全局跟踪及统计变量
    current_protagonist = None
    total_tracked = 0

    veh_stats = {}

    completed_vehicles = 0
    teleported_vehicles = 0
    TOTAL_VEHICLES = 2500

    current_time = 0
    last_track_time = 0.0

    plotter = MultiprocessingPlotter("场景 A - 无预订监控面板")
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
                        if v in veh_stats
                        and veh_stats[v].get("status") in ["driving", "cruising"]
                    ]

                    if struggling_candidates:
                        current_protagonist = random.choice(struggling_candidates)
                        total_tracked += 1

                        msg = "\n" + "=" * 60
                        msg += f"🎬 [镜头切角] 第 {total_tracked} 位司机: {current_protagonist} 的寻找车位"
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
                        if time.time() - last_track_time > 20.0:
                            traci.gui.trackVehicle("View #0", current_protagonist)
                            traci.gui.setZoom("View #0", 2000)
                            last_track_time = time.time()
                    else:
                        last_track_time = time.time()
                except Exception:
                    pass

        # ---------------------------------------------------------------------
        # 新生成车辆的处理
        # ---------------------------------------------------------------------
        for vid in traci.simulation.getDepartedIDList():
            try:
                traci.vehicle.setShapeClass(vid, "passenger")

                traci.vehicle.subscribe(
                    vid,
                    [
                        tc.VAR_FUELCONSUMPTION,
                        tc.VAR_DISTANCE,
                        tc.VAR_ROAD_ID,
                        tc.VAR_SPEED,
                        tc.VAR_POSITION,
                        tc.VAR_LANEPOSITION,
                    ],
                )

                veh_stats[vid] = {
                    "status": "driving",
                    "target_spot": None,
                    "spawn_time": current_time,
                    "search_time": 0.0,
                    "cruise_start_dist": None,
                    "cruise_start_time": None,
                    "failed_targets": set(),
                    "total_fuel": 0.0,
                    "last_dist": 0.0,
                    "speed": 0.0,
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
                    stats["search_time"] = search_time
                    last_dist = stats.get("last_dist", 0.0)
                    total_fuel = stats.get("total_fuel", 0.0)

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
                current_speed = data[tc.VAR_SPEED]
                current_pos = data[tc.VAR_POSITION]
                current_lanepos = data.get(tc.VAR_LANEPOSITION, 0.0)

                stats["last_dist"] = current_dist
                stats["total_fuel"] = stats.get("total_fuel", 0.0) + current_fuel
                stats["speed"] = current_speed

                try:
                    # 识别成功泊入的车辆并上报数据
                    if traci.vehicle.isStoppedParking(vid):
                        target_spot = stats.get("target_spot")
                        if target_spot:
                            all_spots[target_spot]["occupied"] += 1
                        stats["status"] = "parked"

                        search_time = current_time - (
                            stats.get("cruise_start_time") or stats["spawn_time"]
                        )
                        stats["search_time"] = search_time
                        cruise_dist = (
                            current_dist - stats["cruise_start_dist"]
                            if stats["cruise_start_dist"]
                            else 0
                        )
                        total_fuel = stats.get("total_fuel", 0.0)

                        if vid == current_protagonist:
                            msg = f"🎉 司机 {current_protagonist} 终于停好了！\\n"
                            msg += f"   ✅ 最终落脚点: {target_spot}"
                            traci.simulation.writeMessage(msg)
                            current_protagonist = None

                        cursor.execute(
                            "INSERT INTO Cruising_Logs (vehicle_id, scenario, search_time_sec, cruising_distance_m, total_fuel_mg, final_spot_id) VALUES (%s, %s, %s, %s, %s, %s)",
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

                    # a. 车辆未到达 CBD 区域时状态为 driving，进入后切换为 cruising
                    if stats["status"] == "driving":
                        x, y = current_pos
                        if 800 <= x <= 2000 and 800 <= y <= 2000:
                            stats["status"] = "cruising"
                            stats["cruise_start_dist"] = current_dist
                            stats["cruise_start_time"] = current_time
                            # c. 模拟缓慢行驶、频繁刹车
                            traci.vehicle.setSpeedFactor(vid, 0.4)
                            traci.vehicle.setImperfection(vid, 0.9)

                    # 盲目寻找车位逻辑
                    if stats["status"] == "cruising":
                        # 检查当前或即将到达的edge是否有空车位（肉眼观察）
                        if not stats.get("target_spot"):
                            route = traci.vehicle.getRoute(vid)
                            route_idx = traci.vehicle.getRouteIndex(vid)
                            upcoming_edges = route[route_idx : route_idx + 2]

                            found_spot = None
                            for edge in upcoming_edges:
                                if edge in spots_by_edge:
                                    # 打乱顺序，随机观察一个空车位
                                    spots = spots_by_edge[edge].copy()
                                    random.shuffle(spots)
                                    for sid in spots:
                                        # 过滤掉当前道路上已经开过的车位（增加15米的制动距离余量）
                                        if edge == current_edge and all_spots[sid].get("startPos", 0.0) <= current_lanepos + 15.0:
                                            continue
                                            
                                        if (
                                            all_spots[sid]["occupied"]
                                            < all_spots[sid]["capacity"]
                                        ):
                                            found_spot = sid
                                            break
                                if found_spot:
                                    break

                            if found_spot:
                                # 看到空车位，尝试准备停入
                                try:
                                    traci.vehicle.setParkingAreaStop(
                                        vid, found_spot, duration=7200
                                    )
                                    stats["target_spot"] = found_spot
                                except traci.exceptions.TraCIException:
                                    pass
                            else:
                                # 未找到空车位，检查是否快到目的地，如果是，则需要继续巡航（扩张搜索半径）
                                if route_idx >= len(route) - 2:
                                    cruise_time = current_time - stats.get(
                                        "cruise_start_time", current_time
                                    )
                                    # e. 随着时间增长逐步扩大搜索半径
                                    # 假设每5分钟扩大一圈(200m)，从7x7(600m)开始
                                    steps = int(cruise_time // 300)
                                    radius = 600 + steps * 200
                                    if radius > 1400:
                                        radius = 1400

                                    min_x, max_x = 1400 - radius, 1400 + radius
                                    min_y, max_y = 1400 - radius, 1400 + radius

                                    valid_edges = [
                                        eid
                                        for eid, edata in all_edge_data.items()
                                        if min_x <= edata["tx"] <= max_x
                                        and min_y <= edata["ty"] <= max_y
                                    ]
                                    if not valid_edges:
                                        valid_edges = list(all_edge_data.keys())

                                    new_target = random.choice(valid_edges)
                                    try:
                                        traci.vehicle.changeTarget(vid, new_target)
                                    except:  # noqa: E722
                                        pass

                        else:
                            # 已经锁定了车位，检查是否被抢占
                            target_spot = stats["target_spot"]
                            target_edge = all_spots[target_spot]["edge"]
                            if current_edge == target_edge:
                                if (
                                    all_spots[target_spot]["occupied"]
                                    >= all_spots[target_spot]["capacity"]
                                ):
                                    # 被抢占了，放弃该车位，继续巡航
                                    if current_lanepos <= all_spots[target_spot].get("startPos", 0.0):
                                        try:
                                            traci.vehicle.setParkingAreaStop(
                                                vid, target_spot, duration=0
                                            )
                                        except:
                                            pass
                                    else:
                                        # 如果已经开过了或者到了，说明它可能停下等了或者错过了，强制唤醒继续
                                        try:
                                            traci.vehicle.resume(vid)
                                        except:
                                            pass
                                    stats["target_spot"] = None
                                    if vid == current_protagonist:
                                        traci.simulation.writeMessage(
                                            f"  ❌ {vid} 到达 {target_spot}，但车位已被抢占！继续寻找。"
                                        )

                except traci.exceptions.TraCIException:
                    pass

        plotter.send_data(int(current_time), veh_stats)

        # 验证结束条件：全量车辆处理完毕
        if (completed_vehicles + teleported_vehicles) == TOTAL_VEHICLES:
            h = int(current_time // 3600)
            m = int((current_time % 3600) // 60)
            s = int(current_time % 60)

            print("\n" + "✨" * 30)
            print("🎉 提前完赛！系统已达到 100% 处理率。")
            print(
                f"⏱️ 最后一辆车完成状态变更的全局时间为：{h} 小时 {m} 分 {s} 秒 ({current_time} 秒)"
            )
            print("✨" * 30 + "\n")
            break

        # 每隔 60 秒刷新数据库状态同步信息
        if current_time % 60 == 0:
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
                stats["search_time"] = search_time
                cruise_dist = (
                    traci.vehicle.getDistance(vid) - stats["cruise_start_dist"]
                    if stats["cruise_start_dist"]
                    else 0
                )
                total_fuel = stats.get("total_fuel", 0.0)

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
    plotter.close()
    cursor.close()
    conn.close()


if __name__ == "__main__":
    run_baseline()
