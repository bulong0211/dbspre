"""Simulation configuration constants and paths."""

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "configs"

# ---------------------------------------------------------------------------
# SUMO environment
# ---------------------------------------------------------------------------
if "SUMO_HOME" in os.environ:
    sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))
else:
    sys.exit("Please set the 'SUMO_HOME' environment variable")

from sumolib import checkBinary  # noqa: E402

HAS_GUI = True
sumoBinary = checkBinary("sumo-gui") if HAS_GUI else checkBinary("sumo")
sumoCmd = [sumoBinary, "-c", str(CONFIG_DIR / "demo.sumocfg")]

# ---------------------------------------------------------------------------
# Simulation parameters
# ---------------------------------------------------------------------------
SIMULATION_DURATION_LIMIT = 7200
TOTAL_VEHICLES_TARGET = 2500
PARKING_DURATION = 7200

# ---------------------------------------------------------------------------
# Curbside search parameters
# ---------------------------------------------------------------------------
SIGHT_DISTANCE = 180.0
SPOT_STOP_MARGIN = 3.0
ROUTE_EXHAUSTION_MARGIN = 5
INTERSECTION_LOOKAHEAD = 40.0
TARGET_TIMEOUT = 120

# ---------------------------------------------------------------------------
# Performance parameters
# ---------------------------------------------------------------------------
PARKING_SCAN_INTERVAL = 3
PLOTTER_UPDATE_INTERVAL = 5
GUI_REFRESH_INTERVAL = 3

# ---------------------------------------------------------------------------
# SUMO-GUI tracking
# ---------------------------------------------------------------------------
GUI_ZOOM_DEFAULT = 250
GUI_ZOOM_TRACKED = 2000
TRACK_SWITCH_COOLDOWN = 20.0
TRACKING_VEHICLE_THRESHOLD = 50

# ---------------------------------------------------------------------------
# Screen recording
# ---------------------------------------------------------------------------
ENABLE_SCREEN_RECORDING = True
RECORDING_OUTPUT_DIR = CONFIG_DIR.parent / "recordings"
RECORDING_FPS = 30
RECORDING_PREROLL_SECONDS = 1.0

# ---------------------------------------------------------------------------
# Scenario names
# ---------------------------------------------------------------------------
SCENARIO_A_NAME = "Baseline"
SCENARIO_B_NAME = "Smart_Booking_Priced"

# ---------------------------------------------------------------------------
# Scenario B parameters
# ---------------------------------------------------------------------------
STREET_SPOT_THRESHOLD = 3
UNIT_DIST_COST = 0.0025

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DB_SYNC_INTERVAL = 60
