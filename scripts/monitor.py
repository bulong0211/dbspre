import multiprocessing as mp
import queue
from typing import Dict

import matplotlib
import matplotlib.pyplot as plt


def render_worker(q: mp.Queue, title: str) -> None:
    """
    [独立子进程] 负责 Matplotlib 实时渲染。
    """
    # 解决中文乱码问题
    plt.rcParams["font.sans-serif"] = [
        "SimHei",
        "Microsoft YaHei",
        "Arial Unicode MS",
        "sans-serif",
    ]
    plt.rcParams["axes.unicode_minus"] = False
    matplotlib.use("TkAgg")

    plt.ion()
    fig, axs = plt.subplots(2, 3, figsize=(9.6, 10.8))
    fig.suptitle(title, fontsize=16, fontweight="bold")

    # 初始化数据容器
    steps, cruise_y, parked_y, time_y, fuel_y = [], [], [], [], []
    total_cruise_dist_y, avg_speed_y = [], []

    # 定义子图
    (line_cruise,) = axs[0, 0].plot([], [], "r-", label="游荡车辆")
    axs[0, 0].set_title("实时游荡/寻车数")
    axs[0, 0].set_ylabel("车辆数")
    axs[0, 0].set_xlabel("仿真步长")

    (line_parked,) = axs[0, 1].plot([], [], "g-", label="成功停泊")
    axs[0, 1].set_title("累计成功停泊数")
    axs[0, 1].set_ylabel("停泊数")
    axs[0, 1].set_xlabel("仿真步长")

    (line_total_cruise,) = axs[0, 2].plot([], [], "m-", label="巡航总距离")
    axs[0, 2].set_title("巡航总距离 (km)")
    axs[0, 2].set_ylabel("距离 (km)")
    axs[0, 2].set_xlabel("仿真步长")

    (line_time,) = axs[1, 0].plot([], [], "b-", label="平均耗时")
    axs[1, 0].set_title("平均寻车耗时 (s)")
    axs[1, 0].set_ylabel("时间 (s)")
    axs[1, 0].set_xlabel("仿真步长")

    (line_fuel,) = axs[1, 1].plot([], [], "k-", label="累计油耗")
    axs[1, 1].set_title("系统累计总油耗 (kg)")
    axs[1, 1].set_ylabel("油耗 (kg)")
    axs[1, 1].set_xlabel("仿真步长")

    (line_speed,) = axs[1, 2].plot([], [], "c-", label="平均速度")
    axs[1, 2].set_title("路网平均速度 (m/s)")
    axs[1, 2].set_ylabel("速度 (m/s)")
    axs[1, 2].set_xlabel("仿真步长")

    active_axs = [axs[0, 0], axs[0, 1], axs[0, 2], axs[1, 0], axs[1, 1], axs[1, 2]]

    for ax in active_axs:
        ax.grid(True, linestyle="--", alpha=0.5)

    fig.tight_layout(pad=3.0)

    while True:
        try:
            data = q.get(timeout=1.0)

            # 批量处理队列中所有积压的数据以避免渲染延迟
            batch = [data]
            while True:
                try:
                    d = q.get_nowait()
                    batch.append(d)
                except queue.Empty:
                    break

            stop_received = False
            for d in batch:
                if d == "STOP":
                    stop_received = True
                    continue

                # 更新数据
                steps.append(d["step"])
                cruise_y.append(d["cruising"])
                parked_y.append(d["parked"])
                time_y.append(d["avg_time"])
                fuel_y.append(d["fuel"])
                total_cruise_dist_y.append(d.get("total_cruise_dist", 0))
                avg_speed_y.append(d.get("avg_speed", 0))

            if steps:
                # 动态更新 LineData
                line_cruise.set_data(steps, cruise_y)
                line_parked.set_data(steps, parked_y)
                line_time.set_data(steps, time_y)
                line_fuel.set_data(steps, fuel_y)
                line_total_cruise.set_data(steps, total_cruise_dist_y)
                line_speed.set_data(steps, avg_speed_y)

                # 自动调整坐标轴
                for ax in active_axs:
                    ax.relim()
                    ax.autoscale_view()

                fig.canvas.draw()
                fig.canvas.flush_events()

            if stop_received:
                break
        except queue.Empty:
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
        self.queue = mp.Queue(maxsize=1000)
        self.process = mp.Process(target=render_worker, args=(self.queue, window_title))
        self.process.start()

    def send_data(self, step: int, veh_stats: Dict) -> None:
        """
        提取仿真指标并推入队列。
        """
        # 计算游荡数
        cruising = sum(1 for v in veh_stats.values() if v.get("status") == "cruising")

        # 计算已停车相关指标
        parked_v = [v for v in veh_stats.values() if v.get("status") == "parked"]
        parked_count = len(parked_v)

        # 计算平均寻车耗时
        avg_time = (
            sum(v.get("search_time", 0) for v in parked_v) / parked_count
            if parked_count > 0
            else 0
        )

        # 计算总油耗 (mg -> kg)
        total_fuel = sum(v.get("total_fuel", 0) for v in veh_stats.values()) / 1000000.0

        # 计算巡航总距离 (m -> km)
        total_cruise_dist = 0.0
        for v in veh_stats.values():
            start_dist = v.get("cruise_start_dist")
            if start_dist is not None:
                total_cruise_dist += max(0.0, v.get("last_dist", 0.0) - start_dist)
        total_cruise_dist /= 1000.0

        # 计算路网平均速度 (m/s)
        active_veh = [
            v for v in veh_stats.values() if v.get("status") in ["driving", "cruising"]
        ]
        avg_speed = (
            sum(v.get("speed", 0.0) for v in active_veh) / len(active_veh)
            if active_veh
            else 0.0
        )

        payload = {
            "step": step,
            "cruising": cruising,
            "parked": parked_count,
            "avg_time": avg_time,
            "fuel": total_fuel,
            "total_cruise_dist": total_cruise_dist,
            "avg_speed": avg_speed,
        }
        try:
            self.queue.put_nowait(payload)
        except queue.Full:
            pass

    def close(self):
        self.queue.put("STOP")
        self.process.join()
