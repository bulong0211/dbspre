"""GUI 镜头追踪逻辑。"""
import random
import time
import traci
import traci.exceptions

from .config import (
    HAS_GUI, GUI_ZOOM_DEFAULT, GUI_ZOOM_TRACKED,
    TRACK_SWITCH_COOLDOWN, TRACKING_VEHICLE_THRESHOLD,
    GUI_REFRESH_INTERVAL,
)


class GUITracker:
    """管理 SUMO-GUI 中镜头跟随车辆的行为。"""

    def __init__(self):
        """初始化镜头当前主角和节流计数器。"""
        self.protagonist = None
        self.total_tracked = 0
        self.last_track_time = 0.0
        self._step_counter = 0

    def update(self, active_vehicles, veh_stats, current_time):
        """每步调用，但实际逻辑仅每 GUI_REFRESH_INTERVAL 步执行一次。"""
        if not HAS_GUI:
            return
        self._step_counter += 1
        if self._step_counter % GUI_REFRESH_INTERVAL != 0:
            return

        # 主角丢失则重新选角
        if self.protagonist is None or self.protagonist not in active_vehicles:
            if len(active_vehicles) > TRACKING_VEHICLE_THRESHOLD:
                candidates = [
                    v for v in active_vehicles
                    if v in veh_stats
                    and veh_stats[v].get("status") in ("driving", "cruising")
                ]
                if candidates:
                    self.protagonist = random.choice(candidates)
                    self.total_tracked += 1
                    traci.simulation.writeMessage(
                        f"\n{'='*60}\n"
                        f"🎬 [镜头跟随] 第 {self.total_tracked} 位司机: {self.protagonist} 的寻找车位之旅\n"
                        f"{'='*60}"
                    )
                    self._track()
                else:
                    self._untrack()
        else:
            # 防止 SUMO 内部丢失追踪状态
            try:
                if traci.gui.getTrackedVehicle("View #0") == "":
                    if time.time() - self.last_track_time > TRACK_SWITCH_COOLDOWN:
                        self._track()
                else:
                    self.last_track_time = time.time()
            except traci.exceptions.TraCIException:
                pass

    @property
    def current_protagonist(self):
        """返回当前被 SUMO-GUI 跟随的车辆 ID。"""
        return self.protagonist

    def on_vehicle_parked(self, vid):
        """当前主角停车后释放镜头，等待下次重新选车。"""
        if vid == self.protagonist:
            self.protagonist = None

    def _track(self):
        """将 SUMO-GUI 镜头绑定到当前主角车辆。"""
        try:
            traci.gui.trackVehicle("View #0", self.protagonist)
            traci.gui.setZoom("View #0", GUI_ZOOM_TRACKED)
            self.last_track_time = time.time()
        except traci.exceptions.TraCIException:
            pass

    def _untrack(self):
        """清除 SUMO-GUI 车辆跟随并恢复默认缩放。"""
        try:
            traci.gui.trackVehicle("View #0", "")
            traci.gui.setZoom("View #0", GUI_ZOOM_DEFAULT)
        except traci.exceptions.TraCIException:
            pass
