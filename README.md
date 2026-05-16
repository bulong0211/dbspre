<h1 align="center">ITS 智能停车分配与巡航减少仿真系统</h1>

<p align="center">
  <em>基于 SUMO-GUI、Python TraCI、PostgreSQL、matplotlib 与 Streamlit 的停车策略仿真实验软件</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/SUMO-TraCI-orange.svg" alt="SUMO">
  <img src="https://img.shields.io/badge/Database-PostgreSQL-blue.svg" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Dashboard-Streamlit-green.svg" alt="Streamlit">
</p>

> 多语言文档：中文 | [English](README.en.md) | [한국어](README.ko.md) | [日本語](README.ja.md)

---

## 1. 项目简介

本项目用于研究城市停车搜索行为对交通系统的影响。软件使用 SUMO 构建城市路网和车辆流，通过 Python TraCI 在仿真运行时控制车辆、读取车辆状态并触发停车行为。PostgreSQL 负责保存停车位状态和车辆寻位日志，matplotlib 提供仿真过程实时监控，Streamlit 用于实验结果对比。

项目包含两个可对比的实验场景：

| 场景 | 入口脚本 | 核心逻辑 |
| --- | --- | --- |
| 场景 A：基准盲目寻位 | `scripts/run_scenario_A_baseline.py` | 车辆进入路网后不知道全局车位状态，只能沿街扫描可见范围内的空车位；找不到时继续改道巡航。 |
| 场景 B：智能预订与动态定价 | `scripts/run_scenario_B_smart.py` | 车辆生成时查询数据库，根据距离和当前价格选择可用车位，并提前预订和导航。 |

当前实验中两个场景都能在 2 小时仿真上限内完成全部车辆停放，停放率均为 100%。因此成功率只作为事实陈述，核心比较指标改为“完成全部车辆停放所需的全局仿真时间”。

---

## 2. 软件运行方法

### 2.1 环境要求

- Python 3.10 或更高版本
- SUMO，并设置 `SUMO_HOME`
- PostgreSQL
- ffmpeg，可选，仅在录屏开关开启时需要
- 推荐使用 `uv` 安装依赖

PowerShell 设置 SUMO 示例：

```powershell
$env:SUMO_HOME = "C:\Program Files (x86)\Eclipse\Sumo"
```

### 2.2 数据库配置

项目根目录创建 `.env`：

```env
DB_NAME=smart_parking
DB_USER=postgres
DB_PASSWORD=123456
DB_HOST=localhost
DB_PORT=5432
```

`scripts/core/connection.py` 会读取这些环境变量；如果未设置，则使用上面的默认值。运行前需要先在 PostgreSQL 中创建数据库，例如：

```sql
CREATE DATABASE smart_parking;
```

### 2.3 安装依赖

```powershell
uv sync
```

如果不用 `uv`：

```powershell
python -m pip install -r requirements.txt
```

### 2.4 生成仿真资源并初始化数据库

```powershell
uv run python scripts/prepare_simulation.py
```

该脚本依次执行：

1. `scripts/generate_network.ps1`：生成 SUMO 网格路网。
2. `scripts/generate_parking.py`：生成停车位 XML 和数据库 SQL。
3. `scripts/generate_traffic.py`：生成车辆出行需求。
4. `scripts/init_db.py`：执行 `configs/schema.sql`，创建表并插入初始车位数据。

也可以只初始化数据库：

```powershell
uv run python scripts/init_db.py
```

### 2.5 运行场景实验

运行场景 A：

```powershell
uv run python scripts/run_scenario_A_baseline.py
```

运行场景 B：

```powershell
uv run python scripts/run_scenario_B_smart.py
```

运行结果看板：

```powershell
uv run streamlit run scripts/run_dashboard.py
```

---

## 3. 运行流程

场景脚本的通用执行流程如下：

1. 重置数据库车位状态，必要时清理对应场景日志。
2. 连接 PostgreSQL。
3. 加载 `Parking_Spots`、SUMO 路网和停车区数据。
4. 启动 SUMO-GUI。
5. 创建 matplotlib 实时监控窗口。
6. 若 `ENABLE_SCREEN_RECORDING=True`，自动启动 ffmpeg 录制。
7. 进入 `traci.simulationStep()` 主循环。
8. 每步处理新车、车辆状态、停车事件、燃油和距离指标。
9. 按 `DB_SYNC_INTERVAL` 同步车位状态到数据库。
10. 将场景运行摘要写入 `Simulation_Runs`，记录完成全部停放所需仿真时间、总车辆数、成功数、失败数和停放率。
11. 仿真结束或中断时关闭录制、TraCI、监控窗口和数据库连接。

录制开关位于 `scripts/core/config.py`：

```python
ENABLE_SCREEN_RECORDING = True
RECORDING_OUTPUT_DIR = CONFIG_DIR.parent / "recordings"
RECORDING_FPS = 30
RECORDING_PREROLL_SECONDS = 1.0
```

录制输出目录 `recordings/` 已被 `.gitignore` 忽略。

---

## 4. 数据库设计

数据库结构由 `configs/schema.sql` 定义，核心包含一个枚举类型和三张表。

### 4.1 枚举类型：`spot_category`

```sql
CREATE TYPE spot_category AS ENUM ('on-street', 'off-street');
```

用于区分路内停车位和路外停车场。

### 4.2 表：`Parking_Spots`

保存停车位或停车区的静态属性和实时状态。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `spot_id` | `VARCHAR(50)` | 主键，SUMO 停车区 ID。 |
| `edge_id` | `VARCHAR(50)` | 所属 SUMO 道路边 ID。 |
| `spot_type` | `spot_category` | `on-street` 或 `off-street`。 |
| `capacity` | `INT` | 车位容量。 |
| `occupied` | `INT` | 当前占用或预订数量。 |
| `base_price` | `DECIMAL(5,2)` | 基础价格。 |
| `current_price` | `DECIMAL(5,2)` | 场景 B 中实时更新的动态价格。 |

### 4.3 表：`Cruising_Logs`

保存每辆车的寻位结果。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `log_id` | `SERIAL` | 主键。 |
| `vehicle_id` | `VARCHAR(50)` | SUMO 车辆 ID。 |
| `scenario` | `VARCHAR(20)` | 场景名称，如 `Baseline` 或 `Smart_Booking_Priced`。 |
| `search_time_sec` | `FLOAT` | 从车辆生成到停车或失败的时间。 |
| `cruising_distance_m` | `FLOAT` | 寻位巡航距离；场景 B 预订模式下写入 0。 |
| `final_spot_id` | `VARCHAR(50)` | 最终停车位；失败或消失时为 `NULL`。 |
| `created_at` | `TIMESTAMP` | 写入时间。 |
| `total_fuel_mg` | `FLOAT` | 寻位过程累计燃油消耗。 |

### 4.4 表：`Simulation_Runs`

保存每次场景运行的全局摘要，用于比较完成全部车辆停放所需的仿真时间。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `run_id` | `SERIAL` | 主键。 |
| `scenario` | `VARCHAR(20)` | 场景名称。 |
| `completion_time_sec` | `FLOAT` | 该场景完成全部已处理车辆停放所需的全局仿真时间。 |
| `total_vehicles` | `INT` | 本次运行处理的车辆数。 |
| `parked_vehicles` | `INT` | 成功停放车辆数。 |
| `failed_vehicles` | `INT` | 失败或消失车辆数。 |
| `parking_rate` | `FLOAT` | 停放率，等于 `parked_vehicles / total_vehicles`。 |
| `created_at` | `TIMESTAMP` | 摘要写入时间。 |

---

## 5. 项目结构

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
│   ├── cbd.poly.xml          # SUMO 多边形/区域辅助文件
│   ├── demo.sumocfg          # SUMO 主配置
│   ├── demo.net.xml          # 路网文件
│   ├── demo.rou.xml          # 车辆路线文件
│   ├── demo.trips.xml        # OD 出行需求
│   ├── gui-settings.xml      # SUMO-GUI 显示配置
│   ├── parking.add.xml       # 停车区配置
│   └── schema.sql            # 数据库结构与初始数据
├── scripts/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py         # 全局配置、SUMO 启动命令与仿真参数
│   │   ├── connection.py     # PostgreSQL 连接
│   │   ├── db_ops.py         # 日志、运行摘要与车位同步
│   │   ├── gui_tracker.py    # SUMO-GUI 镜头跟随
│   │   ├── monitor.py        # matplotlib 实时监控
│   │   ├── parking_logic.py  # 场景 A 沿街寻位逻辑
│   │   ├── recording.py      # ffmpeg 录屏与窗口摆放
│   │   └── reset_db.py       # 数据库状态重置
│   ├── generate_network.ps1  # 路网生成脚本
│   ├── generate_parking.py   # 停车区与 SQL 生成
│   ├── generate_traffic.py   # 交通流生成
│   ├── init_db.py            # 数据库初始化
│   ├── prepare_simulation.py # 一键准备脚本
│   ├── run_dashboard.py      # Streamlit 看板
│   ├── run_scenario_A_baseline.py # 场景 A 主程序
│   └── run_scenario_B_smart.py    # 场景 B 主程序
└── recordings/               # 本地录屏输出，默认不应提交
```

---

## 6. 核心配置参数

主要参数位于 `scripts/core/config.py`。

| 参数 | 默认值 | 作用 |
| --- | --- | --- |
| `CONFIG_DIR` | `configs/` | SUMO 与 SQL 配置目录。 |
| `HAS_GUI` | `True` | 使用 `sumo-gui` 或无界面 `sumo`。 |
| `SIMULATION_DURATION_LIMIT` | `7200` | 最大仿真时间，单位秒。 |
| `TOTAL_VEHICLES_TARGET` | `2500` | 目标车辆数量。 |
| `PARKING_DURATION` | `7200` | 停车持续时间。 |
| `SIGHT_DISTANCE` | `180.0` | 场景 A 沿街可视寻位距离。 |
| `SPOT_STOP_MARGIN` | `3.0` | 尝试停车所需最小前方距离。 |
| `INTERSECTION_LOOKAHEAD` | `40.0` | 路口前方观察距离。 |
| `TARGET_TIMEOUT` | `120` | 锁定目标车位后的超时时间。 |
| `PLOTTER_UPDATE_INTERVAL` | `5` | matplotlib 刷新间隔。 |
| `DB_SYNC_INTERVAL` | `60` | 数据库同步间隔。 |
| `WEIGHT_DISTANCE` | `1.0` | 场景 B 成本函数中的距离权重。 |
| `WEIGHT_PRICE` | `100.0` | 场景 B 成本函数中的价格权重。 |

---

## 7. 模块与函数说明

### 7.1 `scripts/core/connection.py`

| 函数 | 功能 |
| --- | --- |
| `get_db_config()` | 从 `.env` 或环境变量读取 PostgreSQL 连接参数。 |
| `get_db_connection()` | 创建并返回 `psycopg2` 数据库连接对象。 |

### 7.2 `scripts/core/db_ops.py`

| 函数 | 功能 |
| --- | --- |
| `ensure_simulation_runs_table(cursor)` | 确保 `Simulation_Runs` 运行摘要表存在。 |
| `log_cruise(cursor, vid, scenario, search_time, cruise_dist, total_fuel, spot_id)` | 向 `Cruising_Logs` 插入车辆寻位结果。 |
| `log_run_summary(...)` | 向 `Simulation_Runs` 插入场景级运行摘要。 |
| `sync_spots(cursor, conn, spots_data)` | 将场景 A 的 `occupied` 状态批量同步到 `Parking_Spots`。 |
| `sync_spots_priced(cursor, conn, spots_data)` | 将场景 B 的 `occupied` 和 `current_price` 批量同步到数据库。 |

### 7.3 `scripts/core/parking_logic.py`

| 函数 | 功能 |
| --- | --- |
| `reroute_random()` | 为车辆选择新的随机目标道路，避免当前边、对向边和直接相邻边。 |
| `scan_street()` | 根据车辆当前位置、视距、路口观察距离和车位占用状态扫描候选空位。 |
| `try_park()` | 对当前道路车位调用 `setParkingAreaStop`；对其他道路车位先 `changeTarget` 并记录 pending 状态。 |
| `check_pending()` | 车辆到达 pending 车位所在道路后尝试真正停车。 |
| `handle_occupied()` | 目标车位失效、已满或车辆驶离目标道路时取消目标并重新寻路。 |

### 7.4 `scripts/core/gui_tracker.py`

| 类/方法 | 功能 |
| --- | --- |
| `GUITracker` | 管理 SUMO-GUI 镜头跟随车辆。 |
| `update(active_vehicles, veh_stats, current_time)` | 按间隔选择或维护被跟随车辆，并调整 SUMO-GUI 镜头。 |
| `current_protagonist` | 返回当前被跟随车辆 ID。 |
| `on_vehicle_parked(vid)` | 被跟随车辆停车后释放镜头目标。 |

### 7.5 `scripts/core/monitor.py`

| 类/函数 | 功能 |
| --- | --- |
| `MultiprocessingPlotter` | 在独立进程中绘制实时 matplotlib 监控图。 |
| `send_data(step, veh_stats)` | 从车辆状态中提取停车数、平均时间、燃油、速度等指标并发送给绘图进程。 |
| `close()` | 向绘图进程发送停止信号并等待退出。 |
| `_render_full()` | 场景 A 的 6 图监控面板。 |
| `_render_compact()` | 场景 B 的 4 图监控面板。 |

### 7.6 `scripts/core/recording.py`

| 类/函数 | 功能 |
| --- | --- |
| `place_sumo_left_half()` | 在 Windows 上将 SUMO-GUI 窗口移动到屏幕左半侧。 |
| `ScreenRecorder.start()` | 使用 ffmpeg `gdigrab` 开始桌面录制。 |
| `ScreenRecorder.stop()` | 优雅停止 ffmpeg，确保中途退出时尽量产出可用视频。 |
| `prepare_visual_session()` | 执行窗口摆放、启动录制和预热等待。 |

### 7.7 `scripts/core/reset_db.py`

| 函数 | 功能 |
| --- | --- |
| `reset_database(clear_logs=False, scenario_to_clear=None)` | 重置车位占用和价格；可选择清空全部日志或指定场景日志。 |

### 7.8 `scripts/run_scenario_A_baseline.py`

| 函数 | 功能 |
| --- | --- |
| `_load_spots()` | 从数据库和 `parking.add.xml` 加载车位容量、道路和起点位置。 |
| `_load_edges()` | 从 `demo.net.xml` 提取普通道路的端点、节点和长度。 |
| `_build_opposite_map()` | 构造每条道路的对向道路映射。 |
| `_build_outgoing_map()` | 构造每条道路的下游可选道路映射。 |
| `_spots_by_edge()` | 将车位按道路分组，提升沿街扫描效率。 |
| `_init_stats()` | 初始化车辆状态字典。 |
| `_settle()` | 记录成功停车车辆的寻位日志。 |
| `_settle_lost()` | 记录消失或失败车辆的日志。 |
| `_process_vehicle()` | 场景 A 单车步进逻辑：累计指标、扫描车位、停车、超时和重路由。 |
| `run_baseline()` | 场景 A 主入口。 |

### 7.9 `scripts/run_scenario_B_smart.py`

| 函数 | 功能 |
| --- | --- |
| `_load_spots()` | 从数据库加载车位容量、价格和所属道路。 |
| `_compute_positions()` | 在 TraCI 启动后计算停车位道路坐标。 |
| `_build_pricing_index()` | 预计算路边车位街道分组和路外停车场索引，减少每步重复聚合。 |
| `_price_from_rate()` | 根据占用率返回基础价、1.5 倍或 2 倍价格。 |
| `_compute_pricing()` | 按占用率更新动态价格：超过 70% 为 1.5 倍，超过 90% 为 2 倍。 |
| `_find_best_spot()` | 使用 `距离 * WEIGHT_DISTANCE + 价格 * WEIGHT_PRICE` 选择最优车位。 |
| `_assign_vehicle()` | 设置车辆目标道路、停车区停止命令并初始化车辆状态。 |
| `_settle()` | 将车辆结果写入 `Cruising_Logs`。 |
| `_handle_departed()` | 处理新生成车辆并为其分配车位。 |
| `_process_driving()` | 更新行驶车辆指标，检测停车成功或车辆消失。 |
| `run_smart_booking_with_pricing()` | 场景 B 主入口。 |

### 7.10 其他脚本

| 脚本/函数 | 功能 |
| --- | --- |
| `scripts/init_db.py::init_database()` | 读取并执行 `configs/schema.sql`，创建数据库表并写入初始车位数据。 |
| `scripts/prepare_simulation.py::run_step()` | 执行单个准备步骤并检查退出码。 |
| `scripts/prepare_simulation.py::main()` | 串联路网、停车、交通流和数据库初始化。 |
| `scripts/run_dashboard.py::fetch_data()` | 从 `Cruising_Logs` 与 `Simulation_Runs` 聚合场景指标，供 Streamlit 看板使用。 |

---

## 8. 输出数据与指标口径

项目只使用数据库中真实记录的指标：

- 成功停车数量：`final_spot_id IS NOT NULL`
- 失败或消失数量：`final_spot_id IS NULL`
- 平均寻位时间：`AVG(search_time_sec)`
- 完成全部停放时间：`Simulation_Runs.completion_time_sec`
- 停放率：`Simulation_Runs.parking_rate`
- 总油耗：`SUM(total_fuel_mg)`
- 场景 A 巡航距离：`SUM(cruising_distance_m)`

当前实验结果中两个场景均达到 100% 停放率，因此文档、看板和报告不再将成功率作为主要比较指标；核心比较对象是完成全部车辆停放所需的全局仿真时间。

如果某项指标没有被脚本采集或没有写入数据库，就不应在论文、报告或看板中当作实测结果使用。
