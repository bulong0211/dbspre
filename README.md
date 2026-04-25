<h1 align="center">ITS Smart Parking Allocation & Cruising Reduction</h1>

<p align="center">
  <em>智能停车分配与巡航减少仿真系统</em>
</p>

<p align="center">
    <img src="https://img.shields.io/badge/Python-3.14+-blue.svg" alt="Python Version">
    <img src="https://img.shields.io/badge/SUMO-Simulation-orange.svg" alt="SUMO">
    <img src="https://img.shields.io/badge/Database-PostgreSQL-blue.svg" alt="PostgreSQL">
</p>
[TOC]

## 📖 Project Overview (项目简介)

本项目旨在通过结合 **SUMO (Simulation of Urban MObility)** 微观交通仿真软件和 **PostgreSQL** 实时预订数据库，解决城市中心商业区 (CBD) 车辆“绕圈找车位” (Cruising for parking) 的问题。

### ✨ Core Features (核心模块)
- **Parking Schema (停车模式):** 将 SUMO 的停车区域映射到关系型数据库中。
- **Cruising Detection (巡航检测):** 通过 TraCI 接口检测绕圈车辆并记录寻找车位所耗费的时间和燃油。
- **Reservation Engine (预订引擎):** 基于 SQL 状态查询为进入区域的车辆分配并预订可用车位。
- **Price Response (价格响应):** 动态定价机制，当停车位占用率超过 90% 时触发价格上涨，优化系统整体空间分配。
- **Dashboard (可视化效能评估):** 使用 Streamlit 构建数据看板，对比基础盲目寻找与智能预订两种场景的各项核心指标。

## 🗄️ Database Design (数据库设计)

系统使用 **PostgreSQL** 数据库进行实时状态同步。配置文件为根目录下的 `.env`。
主要的表结构及初始化脚本保存在 `configs/schema.sql` 中：

### `Parking_Spots` (车位状态表)
记录所有路外 (off-street) 与路内 (on-street) 停车位的实时状态：
- `spot_id` (VARCHAR): 车位唯一标识符
- `edge_id` (VARCHAR): 车位所在的路段 ID
- `spot_type` (ENUM): `on-street` 或 `off-street`
- `capacity` (INT): 车位最大容量
- `occupied` (INT): 当前已被占用或预订的数量
- `base_price` (DECIMAL): 基础停车费
- `current_price` (DECIMAL): 浪涌动态价格

### `Cruising_Logs` (巡航日志表)
记录每辆车的寻车生命周期及环境代价：
- `log_id` (SERIAL): 日志主键
- `vehicle_id` (VARCHAR): 车辆 ID
- `scenario` (VARCHAR): 场景名称 (如 Baseline, Smart_Booking_Priced)
- `search_time_sec` (FLOAT): 寻找车位消耗的时间 (秒)
- `cruising_distance_m` (FLOAT): 额外的无效巡航距离 (米)
- `final_spot_id` (VARCHAR): 最终停入的车位 (未成功停入则为 NULL)
- `total_fuel_mg` (FLOAT): 寻车过程中消耗的燃油

## 🏗️ Project Structure (项目结构)

```text
dbspre/
├── configs/                     # SUMO 仿真配置文件与 SQL 脚本
│   ├── demo.rou.xml             # 车辆路由配置
│   ├── demo.trips.xml           # 车辆行程起止点
│   ├── optimal_cbd.net.xml      # 城市网格路网
│   ├── parking.add.xml          # 停车场与车位坐标分布
│   └── schema.sql               # 数据库建表与初始数据脚本
├── scripts/                     # 执行与管理脚本
│   ├── analyze_results.py       # 终端输出核心性能指标的统计脚本
│   ├── connection.py            # 数据库连接池模块，负责读取 .env 提供 PostgreSQL 连接对象
│   ├── generate_network.ps1     # 生成网格化城市路网的命令行脚本
│   ├── generate_parking.py      # 生成车位几何分布并输出 XML 与 SQL 的脚本
│   ├── generate_traffic.py      # 自动生成通勤交通流的脚本
│   ├── init_db.py               # 执行 SQL 脚本，初始化并灌入路网停车数据的脚本
│   ├── reset_db.py              # 重置数据库状态，清空历史日志
│   ├── run_dashboard.py         # 启动基于 Streamlit 的数据可视化分析看板
│   ├── run_scenario_A_baseline.py # 运行场景 A：盲目寻车（无预订系统）的基准测试
│   └── run_scenario_B_smart.py    # 运行场景 B：智能动态定价与预订分配仿真
├── requirements.txt             # Python 依赖包列表
└── README.md                    # 项目说明文档
```

## 🚀 Getting Started (从零开始运行)

### Prerequisites (前置要求)
- **Python >= 3.14** (建议使用 `uv` 虚拟环境管理器)
- **PostgreSQL** 本地或远程服务
- **SUMO** 交通仿真软件 (确保已添加至系统 `Path`，并配置好 `SUMO_HOME` 环境变量)
- **VS Code** (推荐的编辑器)。为了让 Pylance 能够正确识别 `scripts` 目录，请在项目根目录创建或修改 `.vscode/settings.json`，写入以下配置：
  ```json
  {
      "python.analysis.extraPaths": ["${workspaceFolder}/scripts"]
  }
  ```

### 1. Clone & Install (克隆与依赖安装)
```bash
git clone https://github.com/bulong0211/dbspre.git
cd dbspre

# 使用 uv 同步并安装依赖 (推荐)
uv sync

# 如果没有 uv，可以使用 pip 根据 requirements.txt 安装依赖:
pip install -r requirements.txt
```

### 2. Configure Database (配置数据库)
复制项目根目录下的 `.env.example` 为 `.env`，并在 `.env` 中填写您的 PostgreSQL 连接信息：
```env
DB_NAME=smart_parking
DB_USER=postgres
DB_PASSWORD=your_password_here
DB_HOST=localhost
DB_PORT=5432
```
> **注意:** 请确保您已经在 PostgreSQL 中创建了对应的数据库 (例如 `smart_parking`)。

### 3. Build Simulation Environment (构建仿真环境数据)
如果在 `configs/` 目录下已有构建好的路网文件则可跳过这部分，若需从头生成请按顺序执行：
```bash
# 1. 生成基础城市路网 (需在 PowerShell 下运行)
./scripts/generate_network.ps1

# 2. 生成停车场和对应的 SQL 数据
uv run scripts/generate_parking.py

# 3. 生成向 CBD 汇聚的交通流数据
uv run scripts/generate_traffic.py
```

### 4. Initialize Database (初始化与重置数据库)
```bash
# 连接数据库并执行 configs/schema.sql 建表并录入预设车位
uv run scripts/init_db.py
```

### 5. Run Simulations (运行对比仿真)
仿真分为场景 A (基准) 和场景 B (智能版)，运行过程中会自动将交互数据和车辆巡航时间/油耗沉淀到数据库中。
```bash
# 运行场景 A：传统盲目寻车模式
uv run scripts/run_scenario_A_baseline.py

# 运行前重置数据库车位状态（避免影响下次仿真）
uv run scripts/reset_db.py

# 运行场景 B：智能预订与动态定价模式
uv run scripts/run_scenario_B_smart.py
```

### 6. View Results & Dashboard (查看评估结果与大屏看板)
通过终端查看统计报告：
```bash
uv run scripts/analyze_results.py
```
启动 Web 可视化仪表盘 (在浏览器中打开提示地址，通常是 `http://localhost:8501`)：
```bash
uv run streamlit run scripts/run_dashboard.py
```

## 🛠️ Scripts Description (脚本功能说明)
- **`generate_network.ps1`**: 调用 SUMO 内置的 `netgenerate` 创建 15x15 的 CBD 网格路网。
- **`generate_parking.py`**: 解析路网文件，使用几何向量计算划分 50 个路外停车场和 800 个路边停车位，写入 `configs/parking.add.xml` 及 `configs/schema.sql`。
- **`generate_traffic.py`**: 基于路网边界与核心区生成 2,500 辆驶向 CBD 的通勤车辆，并建立 `<trips>` 轨迹配置。
- **`init_db.py`**: 连接 PostgreSQL，读取 `schema.sql` 完成表结构创建及车位初始数据的导入。
- **`reset_db.py`**: 用于在不同阶段重置车位状态到未占用，提供 `--all` 标志时清空仿真日志。
- **`run_scenario_A_baseline.py`**: 基于 TraCI 的无引导仿真，车辆盲目随机驶向路网尝试停车，满员即触发继续巡航，并全量记录轨迹与燃油损失。
- **`run_scenario_B_smart.py`**: 智能核心控制流；引入全局数据库字典。根据车位供需 (`>90%` 占用率) 调整浪涌价格，并用综合惩罚函数（距离 + 价格）为新入网车辆预分配车位，消除找位巡航。
- **`run_dashboard.py`**: 基于 `Streamlit` 和 `Plotly` 的可视化面板，对比两大场景的耗时、死锁车辆数及系统级节油效益。