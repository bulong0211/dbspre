import multiprocessing as mp
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
    fig, axs = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle(title, fontsize=16, fontweight="bold")

    # 初始化数据容器
    steps, cruise_y, parked_y, time_y, fuel_y = [], [], [], [], []

    # 定义四组子图
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

    for ax in axs.flat:
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

            # 动态更新 LineData
            line_cruise.set_data(steps, cruise_y)
            line_parked.set_data(steps, parked_y)
            line_time.set_data(steps, time_y)
            line_fuel.set_data(steps, fuel_y)

            # 自动调整坐标轴
            for ax in axs.flat:
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

        payload = {
            "step": step,
            "cruising": cruising,
            "parked": parked_count,
            "avg_time": avg_time,
            "fuel": total_fuel,
        }
        try:
            self.queue.put_nowait(payload)
        except mp.queues.Full:
            pass

    def close(self):
        self.queue.put("STOP")
        self.process.join()
