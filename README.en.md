<h1 align="center">ITS Smart Parking Allocation and Cruising Reduction</h1>

<p align="center">
  <em>Parking strategy simulation software based on SUMO-GUI, Python TraCI, PostgreSQL, matplotlib, and Streamlit</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/SUMO-TraCI-orange.svg" alt="SUMO">
  <img src="https://img.shields.io/badge/Database-PostgreSQL-blue.svg" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Dashboard-Streamlit-green.svg" alt="Streamlit">
</p>

> Documentation: [中文](README.md) | English | [한국어](README.ko.md) | [日本語](README.ja.md)

---

## 1. Project Overview

This project studies the traffic impact of urban parking search behavior. SUMO builds the road network and traffic demand, Python TraCI controls vehicles and reads simulation state, PostgreSQL stores parking state and vehicle search logs, matplotlib provides real-time simulation monitoring, and Streamlit renders experiment comparisons.

The project includes two comparable scenarios:

| Scenario | Entry script | Core logic |
| --- | --- | --- |
| Scenario A: baseline blind search | `scripts/run_scenario_A_baseline.py` | Vehicles do not know the global parking state. They scan only visible roadside spots and keep rerouting when no spot is found. |
| Scenario B: smart reservation and dynamic pricing | `scripts/run_scenario_B_smart.py` | Vehicles query the database at departure, choose an available spot by distance and current price, reserve it, and navigate to it. |

---

## 2. Running the Software

### 2.1 Requirements

- Python 3.10 or later
- SUMO with `SUMO_HOME` configured
- PostgreSQL
- ffmpeg, optional and only needed when recording is enabled
- `uv` is recommended for dependency management

PowerShell example:

```powershell
$env:SUMO_HOME = "C:\Program Files (x86)\Eclipse\Sumo"
```

### 2.2 Database Configuration

Create `.env` in the project root:

```env
DB_NAME=smart_parking
DB_USER=postgres
DB_PASSWORD=123456
DB_HOST=localhost
DB_PORT=5432
```

`scripts/core/connection.py` reads these environment variables. If they are missing, the same values above are used as defaults. Create the database before running the initialization script:

```sql
CREATE DATABASE smart_parking;
```

### 2.3 Install Dependencies

```powershell
uv sync
```

Without `uv`:

```powershell
python -m pip install -r requirements.txt
```

### 2.4 Generate Simulation Assets and Initialize the Database

```powershell
uv run python scripts/prepare_simulation.py
```

This command runs:

1. `scripts/generate_network.ps1`: generate the SUMO grid network.
2. `scripts/generate_parking.py`: generate parking XML and SQL data.
3. `scripts/generate_traffic.py`: generate vehicle demand.
4. `scripts/init_db.py`: execute `configs/schema.sql` and insert initial parking data.

Database-only initialization:

```powershell
uv run python scripts/init_db.py
```

### 2.5 Run Experiments

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

## 3. Runtime Flow

Scenario scripts follow this flow:

1. Reset parking state and optionally clear logs for the target scenario.
2. Connect to PostgreSQL.
3. Load `Parking_Spots`, SUMO network data, and parking area data.
4. Start SUMO-GUI.
5. Create the matplotlib real-time monitor.
6. If `ENABLE_SCREEN_RECORDING=True`, start ffmpeg recording.
7. Enter the `traci.simulationStep()` main loop.
8. Process departures, vehicle state, parking events, fuel, and distance metrics.
9. Sync parking state to PostgreSQL every `DB_SYNC_INTERVAL`.
10. On completion or interruption, close recording, TraCI, plotting, and database resources.

Recording is configured in `scripts/core/config.py`:

```python
ENABLE_SCREEN_RECORDING = True
RECORDING_OUTPUT_DIR = CONFIG_DIR.parent / "recordings"
RECORDING_FPS = 30
RECORDING_PREROLL_SECONDS = 1.0
```

The `recordings/` directory is ignored by git.

---

## 4. Database Design

The database schema is defined in `configs/schema.sql`. It contains one enum type and two main tables.

### 4.1 Enum: `spot_category`

```sql
CREATE TYPE spot_category AS ENUM ('on-street', 'off-street');
```

This distinguishes curbside spaces from off-street parking lots.

### 4.2 Table: `Parking_Spots`

Stores static attributes and live state for parking spaces or parking areas.

| Field | Type | Description |
| --- | --- | --- |
| `spot_id` | `VARCHAR(50)` | Primary key and SUMO parking area ID. |
| `edge_id` | `VARCHAR(50)` | SUMO road edge ID. |
| `spot_type` | `spot_category` | `on-street` or `off-street`. |
| `capacity` | `INT` | Parking capacity. |
| `occupied` | `INT` | Current occupied or reserved count. |
| `base_price` | `DECIMAL(5,2)` | Base parking price. |
| `current_price` | `DECIMAL(5,2)` | Dynamic price updated in Scenario B. |

### 4.3 Table: `Cruising_Logs`

Stores per-vehicle parking search results.

| Field | Type | Description |
| --- | --- | --- |
| `log_id` | `SERIAL` | Primary key. |
| `vehicle_id` | `VARCHAR(50)` | SUMO vehicle ID. |
| `scenario` | `VARCHAR(20)` | Scenario name, such as `Baseline` or `Smart_Booking_Priced`. |
| `search_time_sec` | `FLOAT` | Time from vehicle departure to parking or failure. |
| `cruising_distance_m` | `FLOAT` | Search cruising distance; Scenario B writes 0 because it uses reservation. |
| `final_spot_id` | `VARCHAR(50)` | Final spot ID; `NULL` for failed or missing vehicles. |
| `created_at` | `TIMESTAMP` | Insert timestamp. |
| `total_fuel_mg` | `FLOAT` | Accumulated fuel consumption during search. |

---

## 5. Project Layout

```text
dbspre/
├── configs/
│   ├── demo.sumocfg
│   ├── demo.net.xml
│   ├── demo.rou.xml
│   ├── demo.trips.xml
│   ├── gui-settings.xml
│   ├── parking.add.xml
│   └── schema.sql
├── scripts/
│   ├── core/
│   ├── generate_network.ps1
│   ├── generate_parking.py
│   ├── generate_traffic.py
│   ├── init_db.py
│   ├── prepare_simulation.py
│   ├── run_dashboard.py
│   ├── run_scenario_A_baseline.py
│   └── run_scenario_B_smart.py
└── pyproject.toml
```

---

## 6. Core Configuration

Main parameters are in `scripts/core/config.py`.

| Parameter | Default | Purpose |
| --- | --- | --- |
| `CONFIG_DIR` | `configs/` | SUMO and SQL configuration directory. |
| `HAS_GUI` | `True` | Use `sumo-gui` or headless `sumo`. |
| `SIMULATION_DURATION_LIMIT` | `7200` | Maximum simulation time in seconds. |
| `TOTAL_VEHICLES_TARGET` | `2500` | Target vehicle count. |
| `PARKING_DURATION` | `7200` | Parking stop duration. |
| `SIGHT_DISTANCE` | `180.0` | Visible search distance for Scenario A. |
| `SPOT_STOP_MARGIN` | `3.0` | Minimum forward distance for a feasible stop. |
| `INTERSECTION_LOOKAHEAD` | `40.0` | Intersection look-ahead distance. |
| `TARGET_TIMEOUT` | `120` | Timeout after locking a target spot. |
| `PLOTTER_UPDATE_INTERVAL` | `5` | matplotlib refresh interval. |
| `DB_SYNC_INTERVAL` | `60` | Database sync interval. |
| `WEIGHT_DISTANCE` | `1.0` | Distance weight in Scenario B cost function. |
| `WEIGHT_PRICE` | `100.0` | Price weight in Scenario B cost function. |

---

## 7. Modules and Functions

### 7.1 `scripts/core/connection.py`

| Function | Purpose |
| --- | --- |
| `get_db_config()` | Read PostgreSQL connection settings from `.env` or environment variables. |
| `get_db_connection()` | Create and return a `psycopg2` connection. |

### 7.2 `scripts/core/db_ops.py`

| Function | Purpose |
| --- | --- |
| `log_cruise()` | Insert one vehicle search result into `Cruising_Logs`. |
| `sync_spots()` | Batch-sync Scenario A `occupied` state to `Parking_Spots`. |
| `sync_spots_priced()` | Batch-sync Scenario B `occupied` and `current_price` to the database. |

### 7.3 `scripts/core/parking_logic.py`

| Function | Purpose |
| --- | --- |
| `reroute_random()` | Select a new target edge while avoiding the current, opposite, and adjacent edges. |
| `scan_street()` | Scan candidate vacant spots using vehicle position, visibility distance, intersection look-ahead, and occupancy. |
| `try_park()` | Call `setParkingAreaStop` on the current edge or route to a pending spot on another edge. |
| `check_pending()` | Try to park when a vehicle reaches the edge of its pending spot. |
| `handle_occupied()` | Cancel invalid, full, or missed target spots and reroute the vehicle. |

### 7.4 `scripts/core/gui_tracker.py`

| Class / method | Purpose |
| --- | --- |
| `GUITracker` | Manage SUMO-GUI vehicle camera tracking. |
| `update(active_vehicles, veh_stats, current_time)` | Select or maintain a tracked vehicle and update the SUMO-GUI camera. |
| `current_protagonist` | Return the currently tracked vehicle ID. |
| `on_vehicle_parked(vid)` | Release the tracked vehicle after it parks. |

### 7.5 `scripts/core/monitor.py`

| Class / function | Purpose |
| --- | --- |
| `MultiprocessingPlotter` | Draw real-time matplotlib charts in a separate process. |
| `send_data(step, veh_stats)` | Extract parked count, average time, fuel, speed, and related metrics from vehicle state. |
| `close()` | Stop and join the plotting process. |
| `_render_full()` | Six-panel monitor for Scenario A. |
| `_render_compact()` | Four-panel monitor for Scenario B. |

### 7.6 `scripts/core/recording.py`

| Class / function | Purpose |
| --- | --- |
| `place_sumo_left_half()` | Move SUMO-GUI to the left half of the screen on Windows. |
| `ScreenRecorder.start()` | Start desktop recording through ffmpeg `gdigrab`. |
| `ScreenRecorder.stop()` | Stop ffmpeg gracefully so an interrupted run can still produce a video file. |
| `prepare_visual_session()` | Arrange windows, start recording, and wait for preroll. |

### 7.7 `scripts/core/reset_db.py`

| Function | Purpose |
| --- | --- |
| `reset_database(clear_logs=False, scenario_to_clear=None)` | Reset parking occupancy and prices; optionally clear all logs or one scenario's logs. |

### 7.8 `scripts/run_scenario_A_baseline.py`

| Function | Purpose |
| --- | --- |
| `_load_spots()` | Load parking capacity, edge IDs, and start positions from database and `parking.add.xml`. |
| `_load_edges()` | Extract edge endpoints, nodes, and lengths from `demo.net.xml`. |
| `_build_opposite_map()` | Build opposite-edge lookup. |
| `_build_outgoing_map()` | Build downstream-edge lookup. |
| `_spots_by_edge()` | Group spots by edge for faster street scanning. |
| `_init_stats()` | Initialize per-vehicle state. |
| `_settle()` | Record successful parking results. |
| `_settle_lost()` | Record missing or failed vehicles. |
| `_process_vehicle()` | Process one Scenario A vehicle step: metrics, scan, parking, timeout, and reroute. |
| `run_baseline()` | Main entry for Scenario A. |

### 7.9 `scripts/run_scenario_B_smart.py`

| Function | Purpose |
| --- | --- |
| `_load_spots()` | Load spot capacity, price, and edge data from the database. |
| `_compute_positions()` | Compute edge coordinates for spots after TraCI starts. |
| `_compute_pricing()` | Update prices by occupancy: 1.5x above 70%, 2x above 90%. |
| `_find_best_spot()` | Select the minimum-cost spot using distance and price. |
| `_assign_vehicle()` | Set the route target, parking stop command, and initial vehicle state. |
| `_settle()` | Write vehicle result to `Cruising_Logs`. |
| `_handle_departed()` | Assign spots to newly departed vehicles. |
| `_process_driving()` | Update active vehicles and detect parking success or disappearance. |
| `run_smart_booking_with_pricing()` | Main entry for Scenario B. |

### 7.10 Other Scripts

| Script / function | Purpose |
| --- | --- |
| `scripts/init_db.py::init_database()` | Read and execute `configs/schema.sql`. |
| `scripts/prepare_simulation.py::run_step()` | Run one preparation step and check its exit code. |
| `scripts/prepare_simulation.py::main()` | Chain network, parking, traffic, and database preparation. |
| `scripts/run_dashboard.py::fetch_data()` | Aggregate scenario metrics from `Cruising_Logs` for Streamlit. |

---

## 8. Metrics Policy

The project should report only metrics that are actually recorded in the database:

- Successful parking count: `final_spot_id IS NOT NULL`
- Failed or missing count: `final_spot_id IS NULL`
- Average search time: `AVG(search_time_sec)`
- Total fuel: `SUM(total_fuel_mg)`
- Scenario A cruising distance: `SUM(cruising_distance_m)`

If a metric is not collected or written to the database, it should not be treated as a measured result in reports, papers, or dashboards.
