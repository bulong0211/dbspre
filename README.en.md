<h1 align="center">ITS Smart Parking Allocation and Cruising Reduction</h1>

<p align="center">
  <em>A SUMO, TraCI, PostgreSQL, and real-time visualization project for parking strategy experiments</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/SUMO-TraCI-orange.svg" alt="SUMO">
  <img src="https://img.shields.io/badge/Database-PostgreSQL-blue.svg" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Visualization-Matplotlib%20%7C%20Streamlit-green.svg" alt="Visualization">
</p>

> Documentation: [中文](README.md) | English | [한국어](README.ko.md) | [日本語](README.ja.md)

---

## Overview

This project builds an urban parking simulation with **SUMO-GUI**, controls vehicle behavior through **Python TraCI**, and records parking state plus search outcomes in **PostgreSQL**. The main goal is to compare blind cruising against smart reservation using measurable indicators such as parking search time, successful parking count, fuel consumption, and average network speed.

The current implementation contains two experiment scripts:

| Script | Scenario | Behavior |
| --- | --- | --- |
| `scripts/run_scenario_A_baseline.py` | Scenario A: blind network-wide search | Vehicles enter the network and scan roadside spaces. If no space is available nearby, they keep rerouting and cruising. |
| `scripts/run_scenario_B_smart.py` | Scenario B: smart reservation | Vehicles query the database at spawn time and reserve an available spot selected by distance and dynamic price. |

Both scenario scripts write outcomes to `Cruising_Logs` and update occupancy and price fields in `Parking_Spots`. `scripts/run_dashboard.py` reads the indicators that actually exist in the database and renders the comparison dashboard.

---

## Current Changes

- Added `scripts/core/recording.py` to arrange SUMO-GUI and matplotlib windows and optionally start ffmpeg recording.
- Updated `scripts/core/monitor.py` so the matplotlib window is placed on the right half of the screen and stays responsive even before the simulation loop advances.
- Scenario A and B scripts now stop recording, close TraCI, close the plotter, and close database resources in `finally` blocks.
- `configs/demo.sumocfg` starts SUMO-GUI in a controlled state so the script can arrange windows and warm up recording before stepping the simulation.
- `.gitignore` ignores `recordings/` so local video output is not committed.

---

## Project Layout

```text
dbspre/
├── configs/
│   ├── demo.sumocfg          # Main SUMO configuration
│   ├── demo.net.xml          # Road network
│   ├── demo.rou.xml          # Vehicle routes
│   ├── parking.add.xml       # SUMO parking areas
│   └── schema.sql            # PostgreSQL schema and initial parking data
├── scripts/
│   ├── core/
│   │   ├── config.py         # Global paths, SUMO, database, and recording settings
│   │   ├── db_utils.py       # Database connection and cleanup helpers
│   │   ├── gui_tracker.py    # SUMO-GUI vehicle highlighting and tracking
│   │   ├── monitor.py        # Matplotlib real-time monitor
│   │   ├── parking_logic.py  # Shared parking logic for both scenarios
│   │   └── recording.py      # Window placement and ffmpeg recording
│   ├── run_scenario_A_baseline.py
│   ├── run_scenario_B_smart.py
│   ├── run_dashboard.py
│   ├── generate_parking.py
│   ├── generate_traffic.py
│   └── prepare_simulation.py
├── recordings/               # Local video output, ignored by git
├── pyproject.toml
└── README*.md
```

---

## Requirements

- Python 3.10 or later
- SUMO with `SUMO_HOME` configured
- PostgreSQL
- ffmpeg, optional and only required when `ENABLE_SCREEN_RECORDING=True`
- `uv` is recommended for dependency management; plain `pip` also works

Windows PowerShell example:

```powershell
$env:SUMO_HOME = "C:\Program Files (x86)\Eclipse\Sumo"
```

Create a `.env` file in the project root:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=parking
DB_USER=postgres
DB_PASSWORD=your_password
```

---

## Setup

```powershell
uv sync
```

Without `uv`:

```powershell
python -m pip install -r requirements.txt
```

Generate or refresh simulation assets:

```powershell
uv run python scripts/prepare_simulation.py
```

Before running scenarios, make sure the PostgreSQL database exists and `configs/schema.sql` has been imported.

---

## Running

Scenario A:

```powershell
uv run python scripts/run_scenario_A_baseline.py
```

Scenario B:

```powershell
uv run python scripts/run_scenario_B_smart.py
```

Dashboard:

```powershell
uv run streamlit run scripts/run_dashboard.py
```

---

## Visualization and Recording

Recording is controlled in `scripts/core/config.py`:

```python
ENABLE_SCREEN_RECORDING = True
RECORDING_OUTPUT_DIR = CONFIG_DIR.parent / "recordings"
RECORDING_FPS = 30
RECORDING_PREROLL_SECONDS = 1.0
```

When `ENABLE_SCREEN_RECORDING=True`, the scenario startup sequence is:

1. Start SUMO-GUI without advancing the simulation.
2. Create the matplotlib monitor window.
3. Place SUMO-GUI on the left half of the screen and matplotlib on the right half.
4. Start ffmpeg desktop recording.
5. Wait for `RECORDING_PREROLL_SECONDS`.
6. Start calling `traci.simulationStep()`.
7. Stop recording and close resources in `finally` when the simulation ends or the script exits early.

Video files are written to `recordings/`. Set `ENABLE_SCREEN_RECORDING=False` to run the simulation without recording.

---

## Database Tables

### `Parking_Spots`

Stores the static attributes and live state of parking spaces or parking areas.

| Field | Meaning |
| --- | --- |
| `spot_id` | Unique parking spot or area ID |
| `edge_id` | SUMO road segment |
| `spot_type` | `on-street` or `off-street` |
| `capacity` | Capacity |
| `occupied` | Current occupied or reserved count |
| `base_price` | Base price |
| `current_price` | Current dynamic price |

### `Cruising_Logs`

Stores each vehicle's result from network entry to parking success or failure.

| Field | Meaning |
| --- | --- |
| `vehicle_id` | SUMO vehicle ID |
| `scenario` | Experiment scenario |
| `search_time_sec` | Parking search time |
| `cruising_distance_m` | Parking search distance |
| `final_spot_id` | Final parking spot |
| `total_fuel_mg` | Fuel consumed during search |
| `created_at` | Log timestamp |

---

## Key Parameters

| Parameter | Current use |
| --- | --- |
| `SIGHT_DISTANCE = 180.0` | Visibility threshold in meters for Scenario A roadside search. |
| `DB_SYNC_INTERVAL` | Controls how often simulation state is written back to the database. |
| `PLOTTER_UPDATE_INTERVAL` | Controls matplotlib monitor refresh frequency. |
| `ENABLE_SCREEN_RECORDING` | Enables or disables ffmpeg desktop recording. |
| `RECORDING_PREROLL_SECONDS` | Recording warm-up time before SUMO stepping begins. |

---

## Notes

- Reports and dashboards should use only indicators that are actually recorded in the database.
- ffmpeg recording is currently configured for Windows `gdigrab`; non-Windows environments skip recording automatically.
- SUMO, PostgreSQL, and ffmpeg depend on local environment configuration, so check environment variables, database connectivity, and PATH first when debugging startup issues.
