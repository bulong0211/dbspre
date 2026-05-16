import multiprocessing as mp
import queue
from typing import Dict

import matplotlib
import matplotlib.pyplot as plt


def _place_window_right_half(fig):
    """Place the TkAgg matplotlib window on the right half of the primary screen."""
    manager = getattr(fig.canvas, "manager", None)
    window = getattr(manager, "window", None)
    if window is None:
        return

    try:
        window.update_idletasks()
        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        width = screen_w // 2
        height = screen_h
        x = screen_w - width
        y = 0
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.state("normal")
        fig.canvas.draw_idle()
    except Exception:
        # Window placement is backend/OS dependent; plotting should continue if it fails.
        pass


def _keep_window_responsive(fig):
    """Pump matplotlib/Tk events so the window stays responsive while idle."""
    if not plt.fignum_exists(fig.number):
        return False
    try:
        fig.canvas.flush_events()
        plt.pause(0.01)
    except Exception:
        return False
    return True


def _render_full(q, title):
    """场景 A：6 图面板（含巡航指标）。"""
    plt.rcParams["font.sans-serif"] = [
        "SimHei", "Microsoft YaHei", "Arial Unicode MS", "sans-serif",
    ]
    plt.rcParams["axes.unicode_minus"] = False
    matplotlib.use("TkAgg")

    plt.ion()
    fig, axs = plt.subplots(2, 3, figsize=(9.6, 10.8))
    _place_window_right_half(fig)
    fig.suptitle(title, fontsize=16, fontweight="bold")

    steps, cruise_y, parked_y, time_y, fuel_y = [], [], [], [], []
    total_cruise_dist_y, avg_speed_y = [], []

    (line_cruise,) = axs[0, 0].plot([], [], "r-", label="游荡车辆")
    axs[0, 0].set_title("实时游荡/寻车数")
    axs[0, 0].set_ylabel("车辆数")
    axs[0, 0].set_xlabel("仿真步长")

    (line_parked,) = axs[0, 1].plot([], [], "g-", label="成功停泊")
    axs[0, 1].set_title("累计成功停泊数")
    axs[0, 1].set_ylabel("停泊数")
    axs[0, 1].set_xlabel("仿真步长")

    (line_cruise_dist,) = axs[0, 2].plot([], [], "m-", label="巡航总距离")
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
    fig.canvas.draw()
    fig.canvas.flush_events()

    while True:
        try:
            data = q.get(timeout=0.05)
            batch = [data]
            while True:
                try:
                    batch.append(q.get_nowait())
                except queue.Empty:
                    break

            stop_received = False
            for d in batch:
                if d == "STOP":
                    stop_received = True
                    continue
                steps.append(d["step"])
                cruise_y.append(d["cruising"])
                parked_y.append(d["parked"])
                time_y.append(d["avg_time"])
                fuel_y.append(d["fuel"])
                total_cruise_dist_y.append(d.get("total_cruise_dist", 0))
                avg_speed_y.append(d.get("avg_speed", 0))

            if steps:
                line_cruise.set_data(steps, cruise_y)
                line_parked.set_data(steps, parked_y)
                line_time.set_data(steps, time_y)
                line_fuel.set_data(steps, fuel_y)
                line_cruise_dist.set_data(steps, total_cruise_dist_y)
                line_speed.set_data(steps, avg_speed_y)
                for ax in active_axs:
                    ax.relim()
                    ax.autoscale_view()
                fig.canvas.draw()
                if not _keep_window_responsive(fig):
                    break

            if stop_received:
                break
        except queue.Empty:
            if not _keep_window_responsive(fig):
                break
            continue
        except Exception:
            break

    plt.ioff()
    plt.show()


def _render_compact(q, title):
    """场景 B：4 图面板（无巡航指标）。"""
    plt.rcParams["font.sans-serif"] = [
        "SimHei", "Microsoft YaHei", "Arial Unicode MS", "sans-serif",
    ]
    plt.rcParams["axes.unicode_minus"] = False
    matplotlib.use("TkAgg")

    plt.ion()
    fig, axs = plt.subplots(2, 2, figsize=(9.6, 7.2))
    _place_window_right_half(fig)
    fig.suptitle(title, fontsize=16, fontweight="bold")

    steps, parked_y, time_y, fuel_y, avg_speed_y = [], [], [], [], []

    (line_parked,) = axs[0, 0].plot([], [], "g-", label="成功停泊")
    axs[0, 0].set_title("累计成功停泊数")
    axs[0, 0].set_ylabel("停泊数")
    axs[0, 0].set_xlabel("仿真步长")

    (line_time,) = axs[0, 1].plot([], [], "b-", label="平均耗时")
    axs[0, 1].set_title("平均寻车耗时 (s)")
    axs[0, 1].set_ylabel("时间 (s)")
    axs[0, 1].set_xlabel("仿真步长")

    (line_fuel,) = axs[1, 0].plot([], [], "k-", label="累计油耗")
    axs[1, 0].set_title("系统累计总油耗 (kg)")
    axs[1, 0].set_ylabel("油耗 (kg)")
    axs[1, 0].set_xlabel("仿真步长")

    (line_speed,) = axs[1, 1].plot([], [], "c-", label="平均速度")
    axs[1, 1].set_title("路网平均速度 (m/s)")
    axs[1, 1].set_ylabel("速度 (m/s)")
    axs[1, 1].set_xlabel("仿真步长")

    active_axs = [axs[0, 0], axs[0, 1], axs[1, 0], axs[1, 1]]
    for ax in active_axs:
        ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout(pad=3.0)
    fig.canvas.draw()
    fig.canvas.flush_events()

    while True:
        try:
            data = q.get(timeout=0.05)
            batch = [data]
            while True:
                try:
                    batch.append(q.get_nowait())
                except queue.Empty:
                    break

            stop_received = False
            for d in batch:
                if d == "STOP":
                    stop_received = True
                    continue
                steps.append(d["step"])
                parked_y.append(d["parked"])
                time_y.append(d["avg_time"])
                fuel_y.append(d["fuel"])
                avg_speed_y.append(d.get("avg_speed", 0))

            if steps:
                line_parked.set_data(steps, parked_y)
                line_time.set_data(steps, time_y)
                line_fuel.set_data(steps, fuel_y)
                line_speed.set_data(steps, avg_speed_y)
                for ax in active_axs:
                    ax.relim()
                    ax.autoscale_view()
                fig.canvas.draw()
                if not _keep_window_responsive(fig):
                    break

            if stop_received:
                break
        except queue.Empty:
            if not _keep_window_responsive(fig):
                break
            continue
        except Exception:
            break

    plt.ioff()
    plt.show()


_LAYOUTS = {"A": _render_full, "B": _render_compact}


class MultiprocessingPlotter:
    """主进程代理类：负责提取指标并发送至渲染进程。"""

    def __init__(self, window_title: str, layout: str = "A"):
        self._layout = layout
        self.queue = mp.Queue(maxsize=1000)
        worker = _LAYOUTS.get(layout, _render_full)
        self.process = mp.Process(target=worker, args=(self.queue, window_title))
        self.process.start()

    def send_data(self, step: int, veh_stats: Dict) -> None:
        """提取仿真指标并推入队列。"""
        parked_v = [v for v in veh_stats.values() if v.get("status") == "parked"]
        parked_count = len(parked_v)

        avg_time = (
            sum(v.get("search_time", 0) for v in parked_v) / parked_count
            if parked_count > 0 else 0
        )

        total_fuel = sum(v.get("total_fuel", 0) for v in veh_stats.values()) / 1000000.0

        active_veh = [
            v for v in veh_stats.values()
            if v.get("status") in ("cruising", "driving")
        ]
        avg_speed = (
            sum(v.get("speed", 0.0) for v in active_veh) / len(active_veh)
            if active_veh else 0.0
        )

        payload = {
            "step": step,
            "parked": parked_count,
            "avg_time": avg_time,
            "fuel": total_fuel,
            "avg_speed": avg_speed,
        }

        if self._layout == "A":
            cruising = sum(
                1 for v in veh_stats.values()
                if v.get("status") in ("cruising", "driving")
            )
            total_cruise_dist = sum(
                v.get("last_dist", 0.0) for v in veh_stats.values()
            ) / 1000.0
            payload["cruising"] = cruising
            payload["total_cruise_dist"] = total_cruise_dist

        try:
            self.queue.put_nowait(payload)
        except queue.Full:
            pass

    def close(self):
        self.queue.put("STOP")
        self.process.join()
