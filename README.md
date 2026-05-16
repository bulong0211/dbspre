<h1 align="center">ITS 智能停车分配与巡航减少仿真系统</h1>

<p align="center">
  <em>基于 SUMO、TraCI、PostgreSQL 与实时可视化的停车策略对比实验项目</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/SUMO-TraCI-orange.svg" alt="SUMO">
  <img src="https://img.shields.io/badge/Database-PostgreSQL-blue.svg" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Visualization-Matplotlib%20%7C%20Streamlit-green.svg" alt="Visualization">
</p>

> 多语言文档：中文 | [English](README.en.md) | [한국어](README.ko.md) | [日本語](README.ja.md)

---

## 项目概览

本项目使用 **SUMO-GUI** 构建城市路网仿真，通过 **Python TraCI** 控制车辆行为，并使用 **PostgreSQL** 记录停车位状态和车辆寻位结果。项目的核心目标是对比传统盲目寻位模式与智能预订模式在停车巡航时间、成功停车数量、燃油消耗和路网速度上的差异。

当前实现包含两个主要实验脚本：

| 脚本 | 场景 | 行为逻辑 |
| --- | --- | --- |
| `scripts/run_scenario_A_baseline.py` | 场景 A：全路网盲目寻位 | 车辆进入路网后沿街搜索空位；如果当前区域无空位，则继续改道巡航。 |
| `scripts/run_scenario_B_smart.py` | 场景 B：智能预订 | 车辆生成时查询数据库，根据距离和动态价格选择可用车位并提前预订。 |

场景脚本会把结果写入 `Cruising_Logs`，同时更新 `Parking_Spots` 的占用和价格字段。`scripts/run_dashboard.py` 用于从数据库读取真实存在的指标并生成对比看板。

---

## 当前重点变动

- 新增 `scripts/core/recording.py`，用于自动摆放 SUMO-GUI 与 matplotlib 窗口，并按需启动 ffmpeg 录屏。
- `scripts/core/monitor.py` 的 matplotlib 窗口会自动放到屏幕右半侧，并在仿真循环暂未推进时保持响应。
- 场景 A/B 脚本现在在 `finally` 中统一停止录制、关闭 TraCI、关闭可视化进程和数据库连接，减少中途退出后录制文件丢失的问题。
- `configs/demo.sumocfg` 默认启动 SUMO-GUI 后暂停等待脚本控制，便于先完成窗口布局和录屏预热。
- `.gitignore` 已忽略 `recordings/`，避免把本地录屏文件提交到仓库。

---

## 项目结构

```text
dbspre/
├── configs/
│   ├── demo.sumocfg          # SUMO 主配置
│   ├── demo.net.xml          # 路网
│   ├── demo.rou.xml          # 车辆路线
│   ├── parking.add.xml       # SUMO 停车区定义
│   └── schema.sql            # PostgreSQL 表结构与初始车位数据
├── scripts/
│   ├── core/
│   │   ├── config.py         # 全局路径、SUMO、数据库、录屏参数
│   │   ├── db_utils.py       # 数据库连接与清理
│   │   ├── gui_tracker.py    # SUMO-GUI 车辆高亮与跟踪
│   │   ├── monitor.py        # matplotlib 实时监控窗口
│   │   ├── parking_logic.py  # 场景 A/B 共用停车逻辑
│   │   └── recording.py      # 窗口摆放与 ffmpeg 录屏
│   ├── run_scenario_A_baseline.py
│   ├── run_scenario_B_smart.py
│   ├── run_dashboard.py
│   ├── generate_parking.py
│   ├── generate_traffic.py
│   └── prepare_simulation.py
├── recordings/               # 本地录屏输出，已被 git 忽略
├── pyproject.toml
└── README*.md
```

---

## 环境要求

- Python 3.10 或更高版本
- SUMO，并正确设置 `SUMO_HOME`
- PostgreSQL
- ffmpeg，可选，仅在 `ENABLE_SCREEN_RECORDING=True` 时需要
- 推荐使用 `uv` 管理依赖；也可以使用普通 `pip`

Windows PowerShell 示例：

```powershell
$env:SUMO_HOME = "C:\Program Files (x86)\Eclipse\Sumo"
```

数据库连接写入项目根目录 `.env`：

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=parking
DB_USER=postgres
DB_PASSWORD=your_password
```

---

## 安装与准备

```powershell
uv sync
```

如果不使用 `uv`：

```powershell
python -m pip install -r requirements.txt
```

生成或刷新仿真资源：

```powershell
uv run python scripts/prepare_simulation.py
```

该步骤会根据脚本生成停车位、路线和数据库初始化 SQL。运行场景前请确保 PostgreSQL 数据库已经存在，并导入 `configs/schema.sql`。

---

## 运行场景

场景 A：

```powershell
uv run python scripts/run_scenario_A_baseline.py
```

场景 B：

```powershell
uv run python scripts/run_scenario_B_smart.py
```

结果看板：

```powershell
uv run streamlit run scripts/run_dashboard.py
```

---

## 可视化与录屏流程

录屏由 `scripts/core/config.py` 中的开关控制：

```python
ENABLE_SCREEN_RECORDING = True
RECORDING_OUTPUT_DIR = CONFIG_DIR.parent / "recordings"
RECORDING_FPS = 30
RECORDING_PREROLL_SECONDS = 1.0
```

当 `ENABLE_SCREEN_RECORDING=True` 时，场景脚本的启动顺序为：

1. 启动 SUMO-GUI，但暂不推进仿真。
2. 创建 matplotlib 实时监控窗口。
3. 自动把 SUMO-GUI 放到屏幕左半侧，把 matplotlib 放到屏幕右半侧。
4. 启动 ffmpeg 录制桌面。
5. 等待 `RECORDING_PREROLL_SECONDS`。
6. 开始执行 `traci.simulationStep()`。
7. 仿真结束或脚本中途退出时，在 `finally` 中停止录制并关闭资源。

录制文件输出到 `recordings/`。如果不需要录制，将 `ENABLE_SCREEN_RECORDING` 改为 `False` 即可，场景脚本仍会正常运行。

---

## 数据库表

### `Parking_Spots`

记录所有车位或停车区的基础属性与实时状态。

| 字段 | 含义 |
| --- | --- |
| `spot_id` | 车位或停车区唯一 ID |
| `edge_id` | 所属 SUMO 路段 |
| `spot_type` | `on-street` 或 `off-street` |
| `capacity` | 容量 |
| `occupied` | 当前占用或预订数量 |
| `base_price` | 基础价格 |
| `current_price` | 当前动态价格 |

### `Cruising_Logs`

记录车辆从进入路网到完成停车或失败退出的寻位结果。

| 字段 | 含义 |
| --- | --- |
| `vehicle_id` | SUMO 车辆 ID |
| `scenario` | 实验场景名称 |
| `search_time_sec` | 寻位耗时 |
| `cruising_distance_m` | 寻位距离 |
| `final_spot_id` | 最终停车位 |
| `total_fuel_mg` | 寻位期间燃油消耗 |
| `created_at` | 日志写入时间 |

---

## 关键参数

| 参数 | 当前用途 |
| --- | --- |
| `SIGHT_DISTANCE = 180.0` | 场景 A 中车辆沿街观察可用车位的距离阈值，单位为米。 |
| `DB_SYNC_INTERVAL` | 控制仿真状态写回数据库的间隔。 |
| `PLOTTER_UPDATE_INTERVAL` | 控制 matplotlib 监控数据刷新间隔。 |
| `ENABLE_SCREEN_RECORDING` | 是否开启 ffmpeg 桌面录制。 |
| `RECORDING_PREROLL_SECONDS` | 开始推进 SUMO 仿真前的录制预热时间。 |

---

## 说明

- 本项目以数据库中实际记录的指标为准，不在报告或看板中伪造未采集的数据。
- ffmpeg 录制目前按 Windows `gdigrab` 配置；非 Windows 环境会自动跳过录制。
- SUMO、PostgreSQL 和 ffmpeg 都依赖本机环境配置，首次运行时优先检查环境变量、数据库连接和 PATH。
