import atexit
import ctypes
import os
import signal
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from .config import (
    HAS_GUI,
    RECORDING_FPS,
    RECORDING_OUTPUT_DIR,
    RECORDING_PREROLL_SECONDS,
)


def _iter_windows():
    if os.name != "nt":
        return []

    user32 = ctypes.windll.user32
    windows = []

    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value
        if title:
            windows.append((hwnd, title))
        return True

    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(enum_proc(callback), 0)
    return windows


def place_sumo_left_half(timeout=5.0):
    """Move the SUMO-GUI top-level window to the left half of the primary screen."""
    if os.name != "nt" or not HAS_GUI:
        return False

    user32 = ctypes.windll.user32
    deadline = time.time() + timeout
    hwnd = None

    while time.time() < deadline and hwnd is None:
        for candidate, title in _iter_windows():
            lower_title = title.lower()
            if "sumo" in lower_title:
                hwnd = candidate
                break
        if hwnd is None:
            time.sleep(0.1)

    if hwnd is None:
        return False

    screen_w = user32.GetSystemMetrics(0)
    screen_h = user32.GetSystemMetrics(1)
    width = screen_w // 2
    height = screen_h

    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.MoveWindow(hwnd, 0, 0, width, height, True)
    return True


class ScreenRecorder:
    def __init__(self, scenario_name, enabled):
        self.scenario_name = scenario_name
        self.enabled = enabled
        self.process = None
        self.output_path = None
        self._log_file = None
        self._stopped = False
        self._atexit_registered = False

    def start(self):
        if not self.enabled:
            print("Screen recording disabled: ENABLE_SCREEN_RECORDING=False")
            return None
        if os.name != "nt":
            print("Screen recording is only configured for Windows gdigrab; skipping.")
            return None

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            print("ffmpeg was not found on PATH; skipping screen recording.")
            return None

        output_dir = Path(RECORDING_OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(
            c if c.isalnum() or c in ("-", "_") else "_"
            for c in self.scenario_name
        )
        self.output_path = output_dir / f"{safe_name}_{timestamp}.mp4"
        log_path = output_dir / f"{safe_name}_{timestamp}.ffmpeg.log"
        self._log_file = log_path.open("w", encoding="utf-8")

        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "gdigrab",
            "-framerate",
            str(RECORDING_FPS),
            "-i",
            "desktop",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            str(self.output_path),
        ]

        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=self._log_file,
            stderr=self._log_file,
            text=True,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        atexit.register(self.stop)
        self._atexit_registered = True
        print(f"Screen recording started: {self.output_path}")
        return self.output_path

    def stop(self):
        if self._stopped:
            return
        self._stopped = True

        if self.process is None:
            self._close_log()
            self._unregister_atexit()
            return

        if self.process.poll() is None:
            stopped_gracefully = False
            try:
                self.process.communicate(input="q\n", timeout=10)
                stopped_gracefully = True
            except Exception:
                pass

            if not stopped_gracefully and self.process.poll() is None:
                try:
                    if os.name == "nt":
                        self.process.send_signal(signal.CTRL_BREAK_EVENT)
                    else:
                        self.process.terminate()
                    self.process.wait(timeout=5)
                    stopped_gracefully = True
                except Exception:
                    pass

            if not stopped_gracefully and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()

        self._close_log()
        self._unregister_atexit()
        if self.output_path:
            print(f"Screen recording stopped: {self.output_path}")

    def _close_log(self):
        if self._log_file:
            self._log_file.close()
            self._log_file = None

    def _unregister_atexit(self):
        if not self._atexit_registered:
            return
        try:
            atexit.unregister(self.stop)
        except Exception:
            pass
        self._atexit_registered = False


def prepare_visual_session(scenario_name, enable_recording):
    """Arrange windows, optionally start recording, then return the recorder handle."""
    place_sumo_left_half()

    recorder = ScreenRecorder(scenario_name, enable_recording)
    recorder.start()

    if enable_recording:
        time.sleep(RECORDING_PREROLL_SECONDS)

    return recorder
