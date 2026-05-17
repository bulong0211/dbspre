<h1 align="center">ITS 智能停车分配与巡航减少仿真系统</h1>

<p align="center">
  <em>基于 SUMO-GUI、Python TraCI、PostgreSQL、matplotlib 与 Streamlit 的城市停车策略仿真实验软件</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/SUMO-1.26.0-orange.svg" alt="SUMO">
  <img src="https://img.shields.io/badge/PostgreSQL-18.4-blue.svg" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Dashboard-Streamlit-green.svg" alt="Streamlit">
</p>

> 多语言文档：中文 | [English](README.en.md) | [한국어](README.ko.md) | [日本語](README.ja.md)

## 简介

本项目用于评估城市停车寻位行为对交通效率、燃油消耗和排放指标的影响。系统使用 SUMO 生成 15 x 15 城市网格路网，通过 Python TraCI 控制车辆行为，将车位状态、车辆寻位日志和场景级结果写入 PostgreSQL，并用 matplotlib 与 Streamlit 展示仿真过程和运行结果。

项目包含两个可复现实验场景：

| 场景 | 入口脚本 | 核心逻辑 |
| --- | --- | --- |
| 场景 A：基准盲目寻位 | `scripts/run_scenario_A_baseline.py` | 车辆不知道全局车位状态，只能扫描可视范围内的路侧车位；找不到时继续改道巡航。 |
| 场景 B：智能预订与动态定价 | `scripts/run_scenario_B_smart.py` | 车辆生成时查询车位库存，根据 `current_price + estimated_route_distance * UNIT_DIST_COST` 选择统一货币成本最低的车位，并提前预订。 |

## 功能特性

- 使用 SUMO 1.26.0 构建微观交通仿真。
- 使用 PostgreSQL 18.4 持久化停车位、车辆日志和场景摘要。
- 场景 A 实现全路网盲目寻位、目标锁定、超时放弃和随机重路由。
- 场景 B 实现车位预订、分层动态定价和本地路网图距离估算。
- 使用 matplotlib 实时监控仿真过程。
- 使用 Streamlit 从数据库聚合并展示实验结果。

## 环境要求

| 组件 | 版本或要求 |
| --- | --- |
| Python | 3.10 或更高 |
| SUMO | 1.26.0，并配置 `SUMO_HOME` |
| PostgreSQL | 18.4 |
| 依赖管理 | 推荐 `uv`，也可使用 `pip` |

## 快速开始

### 1. 克隆项目

```powershell
git clone https://github.com/bulong0211/dbspre.git
cd dbspre
```

### 2. 安装依赖

```powershell
uv sync
```

如果不使用 `uv`：

```powershell
python -m pip install -r requirements.txt
```

### 3. 配置数据库

在 PostgreSQL 中创建数据库：

```sql
CREATE DATABASE smart_parking;
```

在项目根目录创建 `.env`：

```env
DB_NAME=smart_parking
DB_USER=postgres
DB_PASSWORD=123456
DB_HOST=localhost
DB_PORT=5432
```

### 4. 生成仿真资源并初始化数据库

```powershell
uv run python scripts/prepare_simulation.py
```

该脚本会依次生成 SUMO 路网、停车区、交通需求，并执行 `configs/schema.sql` 初始化数据库。

### 5. 运行仿真实验

```powershell
uv run python scripts/run_scenario_A_baseline.py
uv run python scripts/run_scenario_B_smart.py
```

### 6. 打开结果看板

```powershell
uv run streamlit run scripts/run_dashboard.py
```

## 运行流程

1. 重置数据库中的车位状态和对应场景日志。
2. 连接 PostgreSQL。
3. 加载 `Parking_Spots`、SUMO 路网和停车区数据。
4. 启动 SUMO-GUI 和 matplotlib 监控窗口。
5. 执行 `traci.simulationStep()` 主循环。
6. 处理新车、车辆状态、停车事件、燃油、距离和排放指标。
7. 按 `DB_SYNC_INTERVAL` 将车位状态批量同步到数据库。
8. 将场景摘要写入 `Simulation_Runs`。
9. 仿真结束或中断时关闭 TraCI、监控窗口和数据库连接。

## 数据库设计

数据库结构由 `configs/schema.sql` 定义，核心包含一个枚举类型和三张表。

### `spot_category`

```sql
CREATE TYPE spot_category AS ENUM ('on-street', 'off-street');
```

用于区分路侧停车位和路外停车场。

### `Parking_Spots`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `spot_id` | `VARCHAR(50)` | 主键，SUMO 停车区 ID。 |
| `edge_id` | `VARCHAR(50)` | 所属 SUMO 道路边 ID。 |
| `spot_type` | `spot_category` | `on-street` 或 `off-street`。 |
| `capacity` | `INT` | 车位容量。 |
| `occupied` | `INT` | 当前占用或预订数量。 |
| `base_price` | `DECIMAL(5,2)` | 基础价格。 |
| `current_price` | `DECIMAL(5,2)` | 场景 B 中实时更新的动态价格。 |

### `Cruising_Logs`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `log_id` | `SERIAL` | 主键。 |
| `vehicle_id` | `VARCHAR(50)` | SUMO 车辆 ID。 |
| `scenario` | `VARCHAR(20)` | 场景名称。 |
| `search_time_sec` | `FLOAT` | 从车辆生成到停车或失败的时间。 |
| `cruising_distance_m` | `FLOAT` | 寻位巡航距离；场景 B 预订模式下写入 0。 |
| `final_spot_id` | `VARCHAR(50)` | 最终停车位；失败或消失时为 `NULL`。 |
| `total_fuel_mg` | `FLOAT` | 累计燃油消耗。 |
| `total_co2_mg` | `FLOAT` | 累计二氧化碳排放。 |
| `total_nox_mg` | `FLOAT` | 累计氮氧化物排放。 |
| `total_pmx_mg` | `FLOAT` | 累计颗粒物排放。 |
| `created_at` | `TIMESTAMP` | 写入时间。 |

### `Simulation_Runs`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `run_id` | `SERIAL` | 主键。 |
| `scenario` | `VARCHAR(20)` | 场景名称。 |
| `completion_time_sec` | `FLOAT` | 场景结束时的全局仿真时间。 |
| `total_vehicles` | `INT` | 本次运行处理的车辆数。 |
| `parked_vehicles` | `INT` | 成功停放车辆数。 |
| `failed_vehicles` | `INT` | 失败或消失车辆数。 |
| `parking_rate` | `FLOAT` | `parked_vehicles / total_vehicles`。 |
| `created_at` | `TIMESTAMP` | 摘要写入时间。 |

## 项目结构

```text
dbspre/
├── README.md
├── README.en.md
├── README.ko.md
├── README.ja.md
├── pyproject.toml
├── requirements.txt
├── uv.lock
├── configs/
│   ├── demo.sumocfg
│   ├── demo.net.xml
│   ├── demo.rou.xml
│   ├── demo.trips.xml
│   ├── parking.add.xml
│   └── schema.sql
└── scripts/
    ├── core/
    │   ├── config.py
    │   ├── connection.py
    │   ├── db_ops.py
    │   ├── emissions.py
    │   ├── gui_tracker.py
    │   ├── monitor.py
    │   ├── parking_logic.py
    │   └── reset_db.py
    ├── generate_network.ps1
    ├── generate_parking.py
    ├── generate_traffic.py
    ├── init_db.py
    ├── prepare_simulation.py
    ├── run_dashboard.py
    ├── run_scenario_A_baseline.py
    └── run_scenario_B_smart.py
```

## 核心配置

主要参数位于 `scripts/core/config.py`。

| 参数 | 默认值 | 作用 |
| --- | --- | --- |
| `CONFIG_DIR` | `configs/` | SUMO 与 SQL 配置目录。 |
| `HAS_GUI` | `True` | 使用 `sumo-gui` 或无界面 `sumo`。 |
| `SIMULATION_DURATION_LIMIT` | `7200` | 最大仿真时间，单位秒。 |
| `TOTAL_VEHICLES_TARGET` | `2500` | 目标车辆数量。 |
| `PARKING_DURATION` | `7200` | 停车持续时间。 |
| `SIGHT_DISTANCE` | `180.0` | 场景 A 沿街可视寻位距离。 |
| `TARGET_TIMEOUT` | `120` | 锁定目标车位后的超时时间。 |
| `PLOTTER_UPDATE_INTERVAL` | `5` | matplotlib 刷新间隔。 |
| `DB_SYNC_INTERVAL` | `60` | 数据库同步间隔。 |
| `UNIT_DIST_COST` | `0.0025` | 场景 B 中每米路网距离折算的货币成本。 |

## 模块说明

| 模块 | 作用 |
| --- | --- |
| `scripts/core/connection.py` | 读取 `.env` 并创建 PostgreSQL 连接。 |
| `scripts/core/db_ops.py` | 写入车辆日志、场景摘要并同步车位状态。 |
| `scripts/core/emissions.py` | 累计燃油、CO2、NOx 和 PMx。 |
| `scripts/core/gui_tracker.py` | 控制 SUMO-GUI 镜头跟随车辆。 |
| `scripts/core/monitor.py` | 在独立进程中绘制 matplotlib 实时监控图。 |
| `scripts/core/parking_logic.py` | 实现场景 A 的扫描、停车、超时和重路由逻辑。 |
| `scripts/core/reset_db.py` | 重置车位状态、价格和场景日志。 |
| `scripts/run_scenario_A_baseline.py` | 场景 A 主程序。 |
| `scripts/run_scenario_B_smart.py` | 场景 B 主程序，包含动态定价与智能预订。 |
| `scripts/run_dashboard.py` | Streamlit 数据看板。 |

## 关键函数

| 函数 | 说明 |
| --- | --- |
| `get_db_connection()` | 创建数据库连接。 |
| `log_cruise()` | 写入单车寻位结果。 |
| `log_run_summary()` | 写入场景级摘要。 |
| `sync_spots()` / `sync_spots_priced()` | 批量同步车位状态。 |
| `reroute_random()` | 为场景 A 车辆选择新的随机道路。 |
| `scan_street()` | 扫描可视范围内的路侧车位。 |
| `try_park()` | 尝试将车辆停入目标停车区。 |
| `_load_edge_graph()` | 在场景 B 中从 `demo.net.xml` 构建本地路网图。 |
| `_find_best_spot()` | 根据统一货币成本选择车位。 |
| `_process_driving()` | 更新场景 B 行驶车辆并检测停车结果。 |
| `fetch_data()` | 从数据库聚合 Streamlit 看板指标。 |

## 指标口径

| 指标 | 数据来源 |
| --- | --- |
| 成功停车数量 | `Cruising_Logs.final_spot_id IS NOT NULL` |
| 失败或消失数量 | `Cruising_Logs.final_spot_id IS NULL` |
| 停放率 | `Simulation_Runs.parking_rate` 或车辆日志重新计算值 |
| 仿真结束时间 | `Simulation_Runs.completion_time_sec` |
| 平均寻位时间 | `AVG(Cruising_Logs.search_time_sec)` |
| 巡航距离 | `SUM(Cruising_Logs.cruising_distance_m)` |
| 总油耗 | `SUM(Cruising_Logs.total_fuel_mg)` |
| 总 CO2 | `SUM(Cruising_Logs.total_co2_mg)` |
| 总 NOx | `SUM(Cruising_Logs.total_nox_mg)` |
| 总 PMx | `SUM(Cruising_Logs.total_pmx_mg)` |

## 最新数据库快照

| 指标 | 场景 A：基准盲目寻位 | 场景 B：智能预订 |
| --- | ---: | ---: |
| 计划车辆数 | 2500 | 2500 |
| 成功停放车辆数 | 2498 | 2500 |
| 停放率 | 99.92% | 100.00% |
| 仿真结束时间 | 7200 s | 3922 s |
| 平均寻位/到达时间 | 371.29 s | 108.72 s |
| 巡航距离 | 2692.06 km | 0.00 km |
| 总燃油 | 421.87 kg | 184.58 kg |
| 总 CO2 | 1301.31 kg | 569.37 kg |
| 总 NOx | 413.17 g | 190.02 g |
| 总 PMx | 46.53 g | 46.08 g |
