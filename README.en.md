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
| Scenario B: smart reservation and dynamic pricing | `scripts/run_scenario_B_smart.py` | Vehicles query the database at departure, choose an available spot by route-distance cost and current price, reserve it, and navigate to it. |

Experiment results should be read from the latest database records in `Simulation_Runs` and `Cruising_Logs`. Reports should present parking rate, simulation ending time, average search time, cruising distance, fuel consumption, and persisted emission metrics together instead of turning one run into a permanent conclusion.

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
10. Write a scenario-level summary to `Simulation_Runs`, including completion time, total vehicles, parked vehicles, failed vehicles, and parking rate.
11. On completion or interruption, close recording, TraCI, plotting, and database resources.

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

The database schema is defined in `configs/schema.sql`. It contains one enum type and three main tables.

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
| `total_co2_mg` | `FLOAT` | Accumulated carbon dioxide emissions during search/driving. |
| `total_nox_mg` | `FLOAT` | Accumulated nitrogen oxides emissions. |
| `total_pmx_mg` | `FLOAT` | Accumulated particulate matter emissions. |

### 4.4 Table: `Simulation_Runs`

Stores one global summary per scenario run. The dashboard uses this table to compare the simulation time required to complete parking for all vehicles.

| Field | Type | Description |
| --- | --- | --- |
| `run_id` | `SERIAL` | Primary key. |
| `scenario` | `VARCHAR(20)` | Scenario name. |
| `completion_time_sec` | `FLOAT` | Global simulation time required to complete all processed vehicle parking. |
| `total_vehicles` | `INT` | Number of vehicles processed in the run. |
| `parked_vehicles` | `INT` | Number of successfully parked vehicles. |
| `failed_vehicles` | `INT` | Number of failed or missing vehicles. |
| `parking_rate` | `FLOAT` | Parking rate, equal to `parked_vehicles / total_vehicles`. |
| `created_at` | `TIMESTAMP` | Summary insert timestamp. |

---

## 5. Project Layout

```text
dbspre/
├── .gitignore
├── .python-version
├── pyproject.toml
├── uv.lock
├── README.md
├── README.en.md
├── README.ko.md
├── README.ja.md
├── configs/
│   ├── cbd.poly.xml          # SUMO polygon / area helper file
│   ├── demo.sumocfg          # Main SUMO configuration
│   ├── demo.net.xml          # Road network
│   ├── demo.rou.xml          # Vehicle routes
│   ├── demo.trips.xml        # OD demand
│   ├── gui-settings.xml      # SUMO-GUI view settings
│   ├── parking.add.xml       # Parking area definitions
│   └── schema.sql            # Database schema and initial parking data
├── scripts/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py         # Global config, SUMO command, simulation parameters
│   │   ├── connection.py     # PostgreSQL connection
│   │   ├── db_ops.py         # Logs, run summaries, and spot synchronization
│   │   ├── emissions.py      # Vehicle fuel and persisted emission accumulation
│   │   ├── gui_tracker.py    # SUMO-GUI camera tracking
│   │   ├── monitor.py        # matplotlib real-time monitor
│   │   ├── parking_logic.py  # Scenario A curbside search logic
│   │   ├── recording.py      # ffmpeg recording and window placement
│   │   └── reset_db.py       # Database reset helper
│   ├── generate_network.ps1  # Network generation
│   ├── generate_parking.py   # Parking XML and SQL generation
│   ├── generate_traffic.py   # Traffic demand generation
│   ├── init_db.py            # Database initialization
│   ├── prepare_simulation.py # One-command preparation
│   ├── run_dashboard.py      # Streamlit dashboard
│   ├── run_scenario_A_baseline.py # Scenario A main program
│   └── run_scenario_B_smart.py    # Scenario B main program
└── recordings/               # Local recording output; should not be committed
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
| `UNIT_DIST_COST` | `0.0025` | Monetary cost per meter of route distance in Scenario B, based on fuel cost and driver time cost. |

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
| `ensure_simulation_runs_table(cursor)` | Ensure the `Simulation_Runs` summary table exists. |
| `ensure_cruising_logs_environment_columns(cursor)` | Add missing environmental columns to an existing `Cruising_Logs` table. |
| `log_cruise()` | Insert one vehicle search result into `Cruising_Logs`. |
| `log_run_summary()` | Insert one scenario-level run summary into `Simulation_Runs`. |
| `sync_spots()` | Batch-sync Scenario A `occupied` state to `Parking_Spots`. |
| `sync_spots_priced()` | Batch-sync Scenario B `occupied` and `current_price` to the database. |

### 7.3 `scripts/core/emissions.py`

| Function / constant | Purpose |
| --- | --- |
| `EMISSION_SUB_VARS` | TraCI vehicle subscription variables for fuel, CO2, NOx, and PMx. |
| `init_environment_stats()` | Initialize per-vehicle environmental accumulation fields. |
| `accumulate_environment(stats, data)` | Accumulate one-step TraCI emission data into vehicle state. |
| `environment_log_values(stats)` | Produce environmental values for `Cruising_Logs`. |

### 7.4 `scripts/core/parking_logic.py`

| Function | Purpose |
| --- | --- |
| `reroute_random()` | Select a new target edge while avoiding the current, opposite, and adjacent edges. |
| `scan_street()` | Scan candidate vacant spots using vehicle position, visibility distance, intersection look-ahead, and occupancy. |
| `try_park()` | Call `setParkingAreaStop` on the current edge or route to a pending spot on another edge. |
| `check_pending()` | Try to park when a vehicle reaches the edge of its pending spot. |
| `handle_occupied()` | Cancel invalid, full, or missed target spots and reroute the vehicle. |

### 7.5 `scripts/core/gui_tracker.py`

| Class / method | Purpose |
| --- | --- |
| `GUITracker` | Manage SUMO-GUI vehicle camera tracking. |
| `update(active_vehicles, veh_stats, current_time)` | Select or maintain a tracked vehicle and update the SUMO-GUI camera. |
| `current_protagonist` | Return the currently tracked vehicle ID. |
| `on_vehicle_parked(vid)` | Release the tracked vehicle after it parks. |

### 7.6 `scripts/core/monitor.py`

| Class / function | Purpose |
| --- | --- |
| `MultiprocessingPlotter` | Draw real-time matplotlib charts in a separate process. |
| `send_data(step, veh_stats)` | Extract parked count, average time, fuel, speed, and related metrics from vehicle state. |
| `close()` | Stop and join the plotting process. |
| `_render_full()` | Six-panel monitor for Scenario A. |
| `_render_compact()` | Four-panel monitor for Scenario B. |

### 7.7 `scripts/core/recording.py`

| Class / function | Purpose |
| --- | --- |
| `place_sumo_left_half()` | Move SUMO-GUI to the left half of the screen on Windows. |
| `ScreenRecorder.start()` | Start desktop recording through ffmpeg `gdigrab`. |
| `ScreenRecorder.stop()` | Stop ffmpeg gracefully so an interrupted run can still produce a video file. |
| `prepare_visual_session()` | Arrange windows, start recording, and wait for preroll. |

### 7.8 `scripts/core/reset_db.py`

| Function | Purpose |
| --- | --- |
| `reset_database(clear_logs=False, scenario_to_clear=None)` | Reset parking occupancy and prices; optionally clear all logs or one scenario's logs. |

### 7.9 `scripts/run_scenario_A_baseline.py`

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

### 7.10 `scripts/run_scenario_B_smart.py`

| Function | Purpose |
| --- | --- |
| `_load_spots()` | Load spot capacity, price, and edge data from the database. |
| `_compute_positions()` | Compute edge coordinates for spots after TraCI starts. |
| `_build_pricing_index()` | Precompute curbside street groups and off-street lot indexes to avoid repeated aggregation. |
| `_price_from_rate()` | Return base, 1.5x, or 2x price from an occupancy rate. |
| `_compute_pricing()` | Update prices by occupancy: 1.5x above 70%, 2x above 90%. |
| `_find_best_spot()` | Select the spot with the lowest unified monetary cost, `current_price + estimated_route_distance * UNIT_DIST_COST`, using a local network graph for distance estimation. |
| `_assign_vehicle()` | Set the route target, parking stop command, and initial vehicle state. |
| `_settle()` | Write vehicle result to `Cruising_Logs`. |
| `_handle_departed()` | Assign spots to newly departed vehicles. |
| `_process_driving()` | Update active vehicles and detect parking success or disappearance. |
| `run_smart_booking_with_pricing()` | Main entry for Scenario B. |

### 7.11 Other Scripts

| Script / function | Purpose |
| --- | --- |
| `scripts/init_db.py::init_database()` | Read and execute `configs/schema.sql`. |
| `scripts/prepare_simulation.py::run_step()` | Run one preparation step and check its exit code. |
| `scripts/prepare_simulation.py::main()` | Chain network, parking, traffic, and database preparation. |
| `scripts/run_dashboard.py::fetch_data()` | Aggregate scenario metrics from `Cruising_Logs` and `Simulation_Runs` for Streamlit. |

---

## 8. Metrics Policy

The project should report only metrics that are actually recorded in the database:

- Successful parking count: `final_spot_id IS NOT NULL`
- Failed or missing count: `final_spot_id IS NULL`
- Average search time: `AVG(search_time_sec)`
- Full parking completion time: `Simulation_Runs.completion_time_sec`
- Parking rate: `Simulation_Runs.parking_rate`
- Total fuel: `SUM(total_fuel_mg)`
- Total CO2: `SUM(total_co2_mg)`
- Nitrogen oxides and particulate matter: `SUM(total_nox_mg)`, `SUM(total_pmx_mg)`
- Scenario A cruising distance: `SUM(cruising_distance_m)`

The latest database snapshot is shown below. After a new simulation run, the newest database records should replace these values.

| Metric | Scenario A: baseline blind search | Scenario B: smart reservation |
| --- | ---: | ---: |
| Planned vehicles | 2500 | 2500 |
| Parked vehicles | 2498 | 2500 |
| Parking rate | 99.92% | 100.00% |
| Simulation ending time | 7200 s | 3922 s |
| Average search/arrival time | 371.29 s | 108.72 s |
| Cruising distance | 2692.06 km | 0.00 km |
| Total fuel | 421.87 kg | 184.58 kg |
| Total CO2 | 1301.31 kg | 569.37 kg |
| Total NOx | 413.17 g | 190.02 g |
| Total PMx | 46.53 g | 46.08 g |

If a metric is not collected or written to the database, it should not be treated as a measured result in reports, papers, or dashboards.
