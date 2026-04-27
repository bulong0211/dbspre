import multiprocessing as mp
import math
from typing import Dict

import matplotlib
import matplotlib.pyplot as plt


def render_worker(queue: mp.Queue, title: str) -> None:
    """
    [独立子进程] 负责 Matplotlib 实时渲染。
    """
    # 1. 解决中文乱码问题
    plt.rcParams["font.sans-serif"] = [
        "SimHei",
        "Microsoft YaHei",
        "Arial Unicode MS",
        "sans-serif",
    ]
    plt.rcParams["axes.unicode_minus"] = False
    matplotlib.use("TkAgg")

    plt.ion()
    fig, axs = plt.subplots(3, 3, figsize=(15, 10))
    fig.suptitle(title, fontsize=16, fontweight="bold")

    # 初始化数据容器
    steps, cruise_y, parked_y, time_y, fuel_y = [], [], [], [], []
    total_cruise_dist_y, occupancy_y, avg_price_y = [], [], []

    # 定义子图
    (line_cruise,) = axs[0, 0].plot([], [], "r-", label="游荡车辆")
    axs[0, 0].set_title("🚗 实时游荡/寻车数")
    axs[0, 0].set_ylabel("车辆数")

    (line_parked,) = axs[0, 1].plot([], [], "g-", label="成功停泊")
    axs[0, 1].set_title("✅ 累计成功停泊数")

    (line_time,) = axs[1, 0].plot([], [], "b-", label="平均耗时")
    axs[1, 0].set_title("⏱️ 平均寻车耗时 (秒)")
    axs[1, 0].set_xlabel("仿真步长")

    (line_fuel,) = axs[1, 1].plot([], [], "k-", label="累计油耗")
    axs[1, 1].set_title("🛢️ 系统累计总油耗 (克)")
    axs[1, 1].set_xlabel("仿真步长")

    (line_total_cruise,) = axs[0, 2].plot([], [], "m-", label="巡航总距离")
    axs[0, 2].set_title("🛣️ 巡航总距离 (米)")

    (line_occupancy,) = axs[1, 2].plot([], [], "c-", label="车位占有率")
    axs[1, 2].set_title("🅿️ 车位占有率")

    (line_avg_price,) = axs[2, 0].plot([], [], "y-", label="平均价格")
    axs[2, 0].set_title("💰 停车平均价格 (元)")
    axs[2, 0].set_xlabel("仿真步长")

    # 移除不需要的子图
    fig.delaxes(axs[2, 1])
    fig.delaxes(axs[2, 2])

    active_axs = [axs[0, 0], axs[0, 1], axs[1, 0], axs[1, 1], axs[0, 2], axs[1, 2], axs[2, 0]]

    for ax in active_axs:
        ax.grid(True, linestyle="--", alpha=0.5)

    fig.tight_layout(pad=3.0)

    while True:
        try:
            data = queue.get(timeout=1.0)
            if data == "STOP":
                break

            # 更新数据
            steps.append(data["step"])
            cruise_y.append(data["cruising"])
            parked_y.append(data["parked"])
            time_y.append(data["avg_time"])
            fuel_y.append(data["fuel"])
            total_cruise_dist_y.append(data.get("total_cruise_dist", 0))
            occupancy_y.append(data.get("occupancy", 0))
            avg_price_y.append(data.get("avg_price", 0))

            # 动态更新 LineData
            line_cruise.set_data(steps, cruise_y)
            line_parked.set_data(steps, parked_y)
            line_time.set_data(steps, time_y)
            line_fuel.set_data(steps, fuel_y)
            line_total_cruise.set_data(steps, total_cruise_dist_y)
            line_occupancy.set_data(steps, occupancy_y)
            line_avg_price.set_data(steps, avg_price_y)

            # 自动调整坐标轴
            for ax in active_axs:
                ax.relim()
                ax.autoscale_view()

            fig.canvas.draw()
            fig.canvas.flush_events()
        except mp.queues.Empty:
            continue
        except Exception:
            break

    plt.ioff()
    plt.show()


class MultiprocessingPlotter:
    """
    主进程代理类：负责提取指标并发送至渲染进程。
    """

    def __init__(self, window_title: str):
        self.queue = mp.Queue(maxsize=100)
        self.process = mp.Process(target=render_worker, args=(self.queue, window_title))
        self.process.start()

    def send_data(self, step: int, veh_stats: Dict) -> None:
        """
        提取仿真指标并推入队列。
        """
        if not hasattr(self, "spots_info") or step % 60 == 0:
            import os
            import sys
            
            # 将当前目录加入路径以引入 connection
            current_dir = os.path.dirname(os.path.abspath(__file__))
            if current_dir not in sys.path:
                sys.path.append(current_dir)
            
            try:
                import connection
                with connection.get_db_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT spot_id, capacity, current_price FROM Parking_Spots")
                        self.spots_info = {
                            row[0]: {"capacity": row[1], "price": float(row[2])}
                            for row in cursor.fetchall()
                        }
                        self.total_capacity = sum(info["capacity"] for info in self.spots_info.values())
            except Exception:
                pass

        # 计算游荡数
        cruising = sum(1 for v in veh_stats.values() if v.get("status") == "cruising")
        # 计算已停车相关指标
        parked_v = [v for v in veh_stats.values() if v.get("status") == "parked"]
        parked_count = len(parked_v)
        avg_time = (
            sum(v.get("search_time", 0) for v in parked_v) / parked_count
            if parked_count > 0
            else 0
        )
        # 计算总油耗 (mg -> g)
        total_fuel = sum(v.get("total_fuel", 0) for v in veh_stats.values()) / 1000.0

        # a. 巡航总距离
        total_cruise_dist = 0.0
        for v in veh_stats.values():
            start_dist = v.get("cruise_start_dist")
            if start_dist is not None:
                total_cruise_dist += max(0.0, v.get("last_dist", 0.0) - start_dist)

        # b. 车位占有率
        total_capacity = getattr(self, "total_capacity", 1)
        occupancy = parked_count / total_capacity if total_capacity > 0 else 0.0

        # c. 停车的平均价格
        SIM_END_TIME = 7200
        total_cost = 0.0
        spots_info = getattr(self, "spots_info", {})
        for v in parked_v:
            target_spot = v.get("target_spot")
            price = spots_info.get(target_spot, {}).get("price", 0.0) if target_spot else 0.0
            park_in_time = v.get("spawn_time", 0) + v.get("search_time", 0)
            duration = max(0, SIM_END_TIME - park_in_time)
            
            if duration <= 1800:
                cost = 0.0
            else:
                units = math.ceil(duration / 1800)
                cost = units * price
            total_cost += cost
            
        avg_price = total_cost / parked_count if parked_count > 0 else 0.0

        payload = {
            "step": step,
            "cruising": cruising,
            "parked": parked_count,
            "avg_time": avg_time,
            "fuel": total_fuel,
            "total_cruise_dist": total_cruise_dist,
            "occupancy": occupancy,
            "avg_price": avg_price,
        }
        try:
            self.queue.put_nowait(payload)
        except mp.queues.Full:
            pass

    def close(self):
        self.queue.put("STOP")
        self.process.join()
