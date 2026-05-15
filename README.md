# ITS 智能停车分配与巡航减少仿真系统

<p align="center">
  <em>智能停车预订与动态定价仿真系统</em>
</p>

<p align="center">
    <img src="https://img.shields.io/badge/Python-3.10-blue.svg" alt="Python Version">
    <img src="https://img.shields.io/badge/SUMO-Simulation-orange.svg" alt="SUMO">
    <img src="https://img.shields.io/badge/Database-PostgreSQL-blue.svg" alt="PostgreSQL">
</p>

> **多语言文档 | Multilingual Documentation:** [English](README.en.md) | 中文（默认） | [한국어](README.ko.md) | [日本語](README.ja.md)

---

## 目录

- [项目简介](#项目简介)
- [数据库设计](#数据库设计)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [软件运行方法](#软件运行方法)
- [模块说明](#模块说明)

---

## 项目简介

本项目通过结合 **SUMO**（Simulation of Urban MObility）微观交通仿真软件与 **PostgreSQL** 实时预订数据库，解决城市中心商业区（CBD）车辆"绕圈找车位"（Cruising for Parking）的问题。

**两种场景对比：**

| 场景 | 描述 |
|------|------|
| **A — 基准场景（Baseline）** | 车辆无预订系统，盲目驶入路网，沿街扫描寻找空车位。满员即触发继续巡航。 |
| **B — 智能预订与动态定价（Smart Booking & Pricing）** | 车辆生成时即通过成本函数（距离 + 动态价格）分配最优车位，消除无效巡航。 |

**核心功能：**

- **停车模式** — 将 SUMO 停车区域映射到关系型数据库，实时追踪车位状态。
- **巡航检测** — 通过 TraCI 接口监控每辆车，记录寻找车位所耗费的时间、距离和燃油。
- **预订引擎** — 基于 SQL 状态查询为新入网车辆分配并预订可用车位。
- **动态定价** — 浪涌定价机制：占用率 > 70% 触发 1.5 倍基础价格；> 90% 触发 2 倍。
- **效能大屏** — 基于 Streamlit 的 Web 可视化仪表盘，对比两大场景各项核心指标。

---

## 数据库设计

系统使用 **PostgreSQL** 数据库进行实时状态同步。连接参数在项目根目录 `.env` 文件中配置。数据库模式由 `scripts/generate_parking.py` 自动生成并写入 `configs/schema.sql`。

### 表：`Parking_Spots`（车位状态表）

记录所有路外（off-street）与路内（on-street）停车位的实时状态。

| 列名 | 类型 | 说明 |
|------|------|------|
| `spot_id` | `VARCHAR(50)` | 主键；车位唯一标识符（如 `off_street_0`、`on_street_42`） |
| `edge_id` | `VARCHAR(50)` | 车位所在的道路段（edge）ID |
| `spot_type` | `ENUM('on-street', 'off-street')` | 分类：路内停车 或 路外停车场 |
| `capacity` | `INT` | 车位最大容量 |
| `occupied` | `INT` | 当前已被占用 / 预订的数量（默认 0） |
| `base_price` | `DECIMAL(5,2)` | 基础停车费 |
| `current_price` | `DECIMAL(5,2)` | 浪涌动态价格（场景 B 实时更新） |

### 表：`Cruising_Logs`（巡航日志表）

记录每辆车的寻车生命周期及环境代价。

| 列名 | 类型 | 说明 |
|------|------|------|
| `log_id` | `SERIAL` | 主键；自增 |
| `vehicle_id` | `VARCHAR(50)` | 车辆标识符 |
| `scenario` | `VARCHAR(20)` | 场景名称（`Baseline` 或 `Smart_Booking_Priced`） |
| `search_time_sec` | `FLOAT` | 寻找车位消耗的时间（秒） |
| `cruising_distance_m` | `FLOAT` | 寻找车位行驶的总距离（米） |
| `final_spot_id` | `VARCHAR(50)` | 最终停入的车位（未成功则为 NULL） |
| `total_fuel_mg` | `FLOAT` | 寻车过程中消耗的燃油（毫克） |
| `created_at` | `TIMESTAMP` | 自动生成的日志时间戳 |

---

## 项目结构

```text
dbspre/
├── configs/                          # SUMO 仿真配置文件与 SQL 脚本
│   ├── demo.net.xml                  # 15×15 网格路网
│   ├── demo.rou.xml                  # 车辆路由配置
│   ├── demo.sumocfg                  # SUMO 统一启动配置文件
│   ├── demo.trips.xml                # 车辆行程起止点
│   ├── gui-settings.xml              # SUMO GUI 视觉配置文件
│   ├── parking.add.xml               # 停车场几何与车位分布
│   └── schema.sql                    # 数据库建表与初始数据脚本
├── scripts/                          # Python 脚本
│   ├── core/                         # 共享核心模块
│   │   ├── __init__.py               # 包标记
│   │   ├── config.py                 # 仿真常量与路径配置
│   │   ├── connection.py             # PostgreSQL 连接工厂
│   │   ├── db_ops.py                 # 数据库 CRUD 操作
│   │   ├── gui_tracker.py            # SUMO-GUI 镜头跟踪逻辑
│   │   ├── monitor.py                # 实时 matplotlib 绘图代理
│   │   ├── parking_logic.py          # 沿街寻位逻辑（场景 A）
│   │   └── reset_db.py               # 数据库状态重置工具
│   ├── generate_network.ps1          # PowerShell：通过 netgenerate 生成网格路网
│   ├── generate_parking.py           # 生成停车场和路边车位（XML + SQL）
│   ├── generate_traffic.py           # 生成 2,500 辆驶向 CBD 的通勤车流
│   ├── init_db.py                    # 执行 schema.sql 初始化数据库
│   ├── prepare_simulation.py         # 一键准备：路网 → 停车场 → 车流 → 数据库初始化
│   ├── run_dashboard.py              # Streamlit 性能对比仪表盘
│   ├── run_scenario_A_baseline.py    # 场景 A：盲目巡航（无预订）
│   └── run_scenario_B_smart.py       # 场景 B：智能预订与动态定价
├── .env.example                      # 数据库连接模板
├── requirements.txt                  # Python 依赖列表
└── README.md                         # 本文档
```

---

## 快速开始

### 前置要求

- **Python 3.10**（推荐使用 `uv` 虚拟环境管理器）
- **PostgreSQL** 本地或远程服务
- **SUMO** 交通仿真软件（已添加至系统 `PATH`，并配置 `SUMO_HOME` 环境变量）
- **VS Code**（推荐）。在项目根目录 `.vscode/settings.json` 中添加以下配置以支持 Pylance：

```json
{
    "python.analysis.extraPaths": ["${workspaceFolder}/scripts"]
}
```

### 1. 克隆仓库与安装依赖

```bash
git clone https://github.com/bulong0211/dbspre.git
cd dbspre

# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -r requirements.txt
```

### 2. 配置数据库

复制环境变量模板并填写 PostgreSQL 连接信息：

```bash
cp .env.example .env
```

编辑 `.env`：

```env
DB_NAME=smart_parking
DB_USER=postgres
DB_PASSWORD=your_password_here
DB_HOST=localhost
DB_PORT=5432
```

> **注意：** 请先在 PostgreSQL 中创建对应数据库（如 `CREATE DATABASE smart_parking;`）。

### 3. 准备仿真环境

如果 `configs/` 目录下已有构建好的路网文件可跳过此步。否则运行一键准备脚本：

```bash
uv run scripts/prepare_simulation.py
```

该脚本顺序执行：网络生成 → 停车场生成 → 交通流生成 → 数据库初始化。

### 4. 运行仿真

```bash
# 场景 A — 基准场景（盲目寻车，启动时清空历史日志）
uv run scripts/run_scenario_A_baseline.py

# 场景 B — 智能预订与动态定价
uv run scripts/run_scenario_B_smart.py
```

每个仿真最长运行 7,200 秒（2 小时），或直到全部 2,500 辆车处理完毕。实时指标在 matplotlib 窗口中显示，结果写入 PostgreSQL。

### 5. 查看仪表盘

启动 Streamlit 性能对比大屏：

```bash
uv run streamlit run scripts/run_dashboard.py
```

在浏览器中打开 `http://localhost:8501`，对比两个场景的成功率、寻车时间、油耗和巡航距离。

---

## 软件运行方法

### 仿真流程

两个场景均遵循相同的顶层循环，通过 TraCI 接口与 SUMO 集成：

```
1. 重置数据库状态
2. 连接 PostgreSQL
3. 加载停车位数据
4. 启动 SUMO（使用 demo 配置）
5. 当仿真有活跃车辆且时间 < 7200s 时循环：
   a. 推进一个仿真步长
   b. 更新 GUI 镜头追踪
   c. 处理新生成车辆（分配车位 / 设置路由）
   d. 处理行驶中车辆（更新指标、检测泊车、处理超时）
   e. 刷新实时绘图面板
   f. 检查是否提前完赛（全部 2500 辆车已处理）
   g. 每 60s 同步车位占用与价格至数据库
6. 最终数据库同步
7. 关闭 SUMO、绘图面板和数据库连接
```

### 场景关键差异

| 方面 | 场景 A | 场景 B |
|------|--------|--------|
| 车位分配 | 无（车辆通过街道扫描寻找） | 生成时通过成本函数分配最优车位 |
| 导航方式 | 随机边重路由 | 直接驶向分配车位 |
| 动态定价 | 不使用 | 每步更新浪涌价格 |
| 驾驶行为 | `setSpeedFactor(0.4)`, `setImperfection(0.9)` | 相同参数 |
| 超时处理 | 120s 超时后重路由 | 120s 超时后 teleport 结算 |
| 停车逻辑 | `parking_logic.py`（扫描、尝试停入、重路由） | `changeTarget` + `setParkingAreaStop` |

---

## 模块说明

### `core/config.py` — 配置常量与路径

定义所有可调整的仿真参数。

| 常量 | 值 | 说明 |
|------|-----|------|
| `CONFIG_DIR` | `Path(...)/configs` | SUMO 配置文件路径 |
| `SIMULATION_DURATION_LIMIT` | `7200` | 最大仿真时间（秒） |
| `TOTAL_VEHICLES_TARGET` | `2500` | 需处理的车辆总数 |
| `PARKING_DURATION` | `7200` | 车辆找到车位后的停留时长 |
| `SIGHT_DISTANCE` | `80.0` | 沿街扫描的前方可见距离（米） |
| `SPOT_STOP_MARGIN` | `3.0` | 视为可到达车位的最小前方距离 |
| `ROUTE_EXHAUSTION_MARGIN` | `5` | 触发重路由的剩余边数阈值 |
| `INTERSECTION_LOOKAHEAD` | `40.0` | 路口前扫描交叉方向的距离 |
| `TARGET_TIMEOUT` | `120` | 锁定车位后最长等待时间（秒），超时放弃 |
| `PARKING_SCAN_INTERVAL` | `3` | 完整街道扫描间隔（步数，场景 A） |
| `PLOTTER_UPDATE_INTERVAL` | `5` | 绘图面板刷新间隔（步数） |
| `DB_SYNC_INTERVAL` | `60` | 数据库同步间隔（秒） |
| `SCENARIO_A_NAME` | `"Baseline"` | 场景 A 的数据库标识 |
| `SCENARIO_B_NAME` | `"Smart_Booking_Priced"` | 场景 B 的数据库标识 |
| `STREET_SPOT_THRESHOLD` | `3` | 街道级聚合的最大车位容量（场景 B） |
| `WEIGHT_DISTANCE` | `1.0` | 成本函数中距离的权重系数 |
| `WEIGHT_PRICE` | `100.0` | 成本函数中价格的权重系数 |

#### 核心函数

- `checkBinary(name)` — 定位 SUMO 可执行文件（`sumo` 或 `sumo-gui`）。

---

### `core/connection.py` — 数据库连接工厂

| 函数 | 说明 |
|------|------|
| `get_db_config()` | 从环境变量（`.env`）读取数据库连接参数，返回包含 `dbname`、`user`、`password`、`host`、`port` 的字典。 |
| `get_db_connection()` | 使用 `get_db_config()` 创建并返回 `psycopg2` 连接对象。 |

---

### `core/db_ops.py` — 数据库操作

| 函数 | 签名 | 说明 |
|------|------|------|
| `log_cruise()` | `(cursor, vid, scenario, search_time, cruise_dist, total_fuel, spot_id)` | 向 `Cruising_Logs` 表插入一条车辆寻车结果记录。 |
| `sync_spots()` | `(cursor, conn, spots_data)` | 批量更新所有车位的 `Parking_Spots.occupied`。场景 A 使用。 |
| `sync_spots_priced()` | `(cursor, conn, spots_data)` | 批量更新所有车位的 `occupied` 和 `current_price`。场景 B 使用。 |

---

### `core/gui_tracker.py` — SUMO-GUI 镜头追踪

管理 SUMO-GUI 摄像头跟踪随机选择的"主角"车辆，提供寻车过程的第一人称视角。

| 类 | 说明 |
|----|------|
| `GUITracker` | 跟踪当前主角车辆，管理镜头切换（带可配置冷却时间）。 |

| 方法 | 说明 |
|------|------|
| `__init__()` | 初始化追踪器状态：`protagonist=None`、`total_tracked=0`、`last_track_time=0.0`。 |
| `update(active_vehicles, veh_stats, current_time)` | 每步调用。当前主角丢失时选新主角；SUMO 内部丢失追踪状态时重新应用。受 `GUI_REFRESH_INTERVAL` 节流。 |
| `on_vehicle_parked(vid)` | 主角成功停车后清除主角。 |

| 属性 | 说明 |
|------|------|
| `current_protagonist` | 返回当前追踪的车辆 ID（或 `None`）。 |

---

### `core/monitor.py` — 实时绘图代理

通过独立进程使用 matplotlib 提供仿真指标的实时可视化。

| 类 | 说明 |
|----|------|
| `MultiprocessingPlotter` | 主进程代理类，从车辆状态中提取指标并通过 `multiprocessing.Queue` 发送至后台渲染进程。 |

| 方法 | 说明 |
|------|------|
| `__init__(window_title, layout="A")` | 启动渲染子进程。`layout="A"` 显示 6 图表（含巡航指标）；`layout="B"` 显示 4 图表（停泊数、耗时、油耗、速度）。 |
| `send_data(step, veh_stats)` | 计算当前指标（活跃车辆数、停泊数、平均寻车时间、总油耗、平均速度）并推入渲染队列。 |
| `close()` | 发送 `STOP` 信号并等待渲染进程退出。 |

---

### `core/parking_logic.py` — 沿街寻位逻辑（场景 A）

模拟真实驾驶员在路网中沿道路和路口张望寻找空车位的行为。核心原则：不自行判定车辆能否停入——完全交由 SUMO 的 `setParkingAreaStop` 决定。

| 函数 | 签名 | 说明 |
|------|------|------|
| `reroute_random()` | `(vid, all_edges, opposite_map, outgoing_map)` | 分配随机边作为新目的地，排除当前边、对向边及直接相邻边，确保路由不短于 2 跳。失败返回 `False`。 |
| `scan_street()` | `(vid, current_edge, current_lanepos, spots_by_edge, all_spots, opposite_map, outgoing_map, edge_lengths, full_scan)` | 沿当前道路（以及可选交叉方向与下一路由边）在视野距离内扫描空车位。返回 `(spot_id, spot_edge)` 或 `(None, None)`。 |
| `try_park()` | `(vid, spot_id, spot_edge, stats, current_edge, all_spots)` | 尝试停入发现的车位。同边：调用 `setParkingAreaStop`。异边：调用 `changeTarget` 并记录 pending 预订。已有承诺时拒绝新车位。成功返回 `True`。 |
| `check_pending()` | `(vid, stats, current_edge, all_spots, all_edges, opposite_map, outgoing_map)` | 车辆到达 pending 边后尝试完成停车。若车位已满则清理并重路由。 |
| `handle_occupied()` | `(vid, stats, current_edge, all_spots, all_edges, opposite_map, outgoing_map)` | 检测目标车位被占或车辆已离开目标道路时释放车位并触发重路由。 |

---

### `core/reset_db.py` — 数据库状态重置

| 函数 | 签名 | 说明 |
|------|------|------|
| `reset_database()` | `(clear_logs=False, scenario_to_clear=None)` | 重置 `Parking_Spots.occupied` 为 0、`current_price` 为 `base_price`。若 `clear_logs=True`，清空 `Cruising_Logs` 表。若提供 `scenario_to_clear`，仅删除该场景的日志。 |

---

### `run_scenario_A_baseline.py` — 场景 A：盲目巡航

实现无预订系统的基准场景。车辆被分配随机目的地，必须沿街扫描寻找空车位。

**内部函数：**

| 函数 | 说明 |
|------|------|
| `_load_spots(cursor)` | 从数据库加载停车位元数据，并解析 `parking.add.xml` 获取几何数据（`startPos`、`lane`）。 |
| `_load_edges()` | 解析 `demo.net.xml` 构建道路边字典，包含起止节点坐标和计算长度。 |
| `_build_opposite_map(all_edges)` | 为每条边查找其反向对应边，构建双向映射。 |
| `_build_outgoing_map(all_edges, opposite_map)` | 构建每条边到下游边（排除自身和反向边）的映射。 |
| `_spots_by_edge(all_spots)` | 按父边分组车位 ID，便于高效的街道扫描。 |
| `_init_stats(current_time)` | 为新生成车辆创建初始状态字典。 |
| `_settle(vid, stats, current_time, current_dist, spot_id, cursor, conn)` | 将成功停车的车辆结果写入数据库。 |
| `_settle_lost(vid, stats, current_time, cursor, conn)` | 将丢失/teleport 车辆的结果写入数据库（`final_spot_id = NULL`）。 |
| `_process_vehicle(...)` | 单车辆步进状态机：检查停车状态、处理 pending 车位、沿街扫描、尝试停入、需要时重路由。 |
| `run_baseline()` | 主入口函数，编排完整仿真生命周期。 |

---

### `run_scenario_B_smart.py` — 场景 B：智能预订与动态定价

实现智能场景：车辆生成时通过成本函数分配最优车位，价格根据实时占用率动态调整。

**内部函数：**

| 函数 | 说明 |
|------|------|
| `_load_spots(cursor)` | 从数据库加载带定价信息的停车位数据。 |
| `_compute_positions(all_spots)` | 获取每个停车位所在车道的物理坐标（需 TraCI 运行中）。 |
| `_compute_pricing(all_spots)` | 每仿真步计算浪涌定价。小容量路边车位（≤ 3）按街道聚合计算占用率。定价阶梯：> 90% → 2 倍，> 70% → 1.5 倍，其他为基准价。 |
| `_find_best_spot(vehicle_pos, all_spots)` | 通过最小化 `cost = 距离 × WEIGHT_DISTANCE + 当前价格 × WEIGHT_PRICE` 选择最优车位。仅考虑有空余容量的车位。 |
| `_assign_vehicle(vid, spot_id, all_spots, veh_stats, current_time)` | 通过 `changeTarget` 和 `setParkingAreaStop` 将车辆路由至分配车位。仅在所有 TraCI 调用成功后递增预订计数（原子性）。 |
| `_settle(vid, stats, current_time, spot_id, cursor, conn)` | 将车辆结果写入 `Cruising_Logs` 表。 |
| `_handle_departed(departed, all_spots, veh_stats, current_time)` | 处理新生成车辆：配置驾驶参数、寻找最佳车位并分配。分配失败时输出警告。 |
| `_process_driving(veh_stats, sub_results, current_time, all_spots, cursor, conn, gui)` | 每步处理所有行驶中车辆：更新速度/距离/油耗指标、检测 teleport、执行超时放弃（释放卡住车辆）、检测成功停车。 |
| `run_smart_booking_with_pricing()` | 主入口函数，编排完整仿真生命周期。 |

---

### 辅助脚本

| 脚本 | 说明 |
|------|------|
| `generate_network.ps1` | 调用 SUMO `netgenerate` 创建 15×15 CBD 网格路网。 |
| `generate_parking.py` | 解析路网，生成 50 个路外停车场（每个 38 车位）和 800 个路边车位（每个 1 车位），输出 `parking.add.xml` 和 `schema.sql`。 |
| `generate_traffic.py` | 生成 2,500 辆从边界入口驶向 CBD 核心区的通勤行程，按出发时间排序，输出 `demo.trips.xml`。 |
| `init_db.py` | 连接 PostgreSQL，执行 `schema.sql` 创建表并插入初始车位数据。 |
| `prepare_simulation.py` | 一键准备编排器，顺序执行路网生成 → 停车场生成 → 车流生成 → 数据库初始化。 |
| `run_dashboard.py` | Streamlit Web 仪表盘，查询 `Cruising_Logs` 并渲染场景 A vs 场景 B 的对比 KPI 卡片和图表（成功率、寻车时间、油耗、巡航距离）。 |

| 函数（仪表盘） | 说明 |
|---------------|------|
| `fetch_data()` | 查询 PostgreSQL 按场景聚合的仿真指标数据，缓存 5 秒。 |
