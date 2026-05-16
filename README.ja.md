<h1 align="center">ITS スマート駐車割り当てと巡航削減シミュレーション</h1>

<p align="center">
  <em>SUMO-GUI、Python TraCI、PostgreSQL、matplotlib、Streamlit に基づく駐車戦略シミュレーションソフトウェア</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/SUMO-TraCI-orange.svg" alt="SUMO">
  <img src="https://img.shields.io/badge/Database-PostgreSQL-blue.svg" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Dashboard-Streamlit-green.svg" alt="Streamlit">
</p>

> ドキュメント: [中文](README.md) | [English](README.en.md) | [한국어](README.ko.md) | 日本語

---

## 1. プロジェクト概要

本プロジェクトは、都市における駐車探索行動が交通システムに与える影響を分析するためのソフトウェアです。SUMO は道路網と交通需要を構築し、Python TraCI は車両制御と状態取得を行い、PostgreSQL は駐車状態と車両探索ログを保存します。matplotlib はリアルタイム監視を提供し、Streamlit は実験結果比較ダッシュボードを表示します。

比較可能な 2 つのシナリオがあります。

| シナリオ | 実行スクリプト | コアロジック |
| --- | --- | --- |
| シナリオ A: 基準の盲目的探索 | `scripts/run_scenario_A_baseline.py` | 車両は全体の駐車状態を知らず、可視範囲内の路上駐車スペースだけを探します。空きがなければ経路変更を続けます。 |
| シナリオ B: スマート予約と動的価格 | `scripts/run_scenario_B_smart.py` | 車両出発時にデータベースを照会し、距離と現在価格に基づいて利用可能なスペースを選択して予約します。 |

現在の実験では、両シナリオとも 2 時間のシミュレーション上限内に全車両の駐車を完了し、駐車率はいずれも 100% です。そのため駐車率は事実として示すだけにし、主な比較指標は全車両の駐車完了に必要な全体シミュレーション時間とします。

---

## 2. ソフトウェア実行方法

### 2.1 要件

- Python 3.10 以上
- `SUMO_HOME` が設定された SUMO
- PostgreSQL
- ffmpeg、省略可能。録画有効時のみ必要
- 依存関係管理には `uv` を推奨

PowerShell 例:

```powershell
$env:SUMO_HOME = "C:\Program Files (x86)\Eclipse\Sumo"
```

### 2.2 データベース設定

プロジェクトルートに `.env` を作成します。

```env
DB_NAME=smart_parking
DB_USER=postgres
DB_PASSWORD=123456
DB_HOST=localhost
DB_PORT=5432
```

`scripts/core/connection.py` がこれらの値を読み取ります。未設定の場合は上記の既定値が使われます。初期化スクリプト実行前にデータベースを作成してください。

```sql
CREATE DATABASE smart_parking;
```

### 2.3 依存関係のインストール

```powershell
uv sync
```

`uv` を使わない場合:

```powershell
python -m pip install -r requirements.txt
```

### 2.4 シミュレーション資産生成とデータベース初期化

```powershell
uv run python scripts/prepare_simulation.py
```

このコマンドは以下を実行します。

1. `scripts/generate_network.ps1`: SUMO グリッド道路網を生成。
2. `scripts/generate_parking.py`: 駐車 XML と SQL データを生成。
3. `scripts/generate_traffic.py`: 車両需要を生成。
4. `scripts/init_db.py`: `configs/schema.sql` を実行し、初期駐車データを挿入。

データベースのみ初期化する場合:

```powershell
uv run python scripts/init_db.py
```

### 2.5 実験実行

シナリオ A:

```powershell
uv run python scripts/run_scenario_A_baseline.py
```

シナリオ B:

```powershell
uv run python scripts/run_scenario_B_smart.py
```

ダッシュボード:

```powershell
uv run streamlit run scripts/run_dashboard.py
```

---

## 3. 実行フロー

シナリオスクリプトの共通フローは次の通りです。

1. 駐車状態をリセットし、必要に応じて対象シナリオのログを削除します。
2. PostgreSQL に接続します。
3. `Parking_Spots`、SUMO 道路網、駐車エリアデータを読み込みます。
4. SUMO-GUI を起動します。
5. matplotlib リアルタイムモニターを作成します。
6. `ENABLE_SCREEN_RECORDING=True` の場合、ffmpeg 録画を開始します。
7. `traci.simulationStep()` メインループに入ります。
8. 出発車両、車両状態、駐車イベント、燃料、距離指標を処理します。
9. `DB_SYNC_INTERVAL` ごとに駐車状態を PostgreSQL に同期します。
10. `Simulation_Runs` にシナリオ実行サマリーを書き込みます。完了時間、総車両数、成功数、失敗数、駐車率を含みます。
11. 完了または中断時に録画、TraCI、プロッター、DB 接続を閉じます。

録画設定は `scripts/core/config.py` にあります。

```python
ENABLE_SCREEN_RECORDING = True
RECORDING_OUTPUT_DIR = CONFIG_DIR.parent / "recordings"
RECORDING_FPS = 30
RECORDING_PREROLL_SECONDS = 1.0
```

`recordings/` ディレクトリは git で無視されます。

---

## 4. データベース設計

データベース構造は `configs/schema.sql` で定義され、1 つの enum 型と 3 つの主要テーブルを含みます。

### 4.1 Enum: `spot_category`

```sql
CREATE TYPE spot_category AS ENUM ('on-street', 'off-street');
```

路上駐車スペースと路外駐車場を区別します。

### 4.2 テーブル: `Parking_Spots`

駐車スペースまたは駐車エリアの静的属性とリアルタイム状態を保存します。

| フィールド | 型 | 説明 |
| --- | --- | --- |
| `spot_id` | `VARCHAR(50)` | 主キー、SUMO 駐車エリア ID。 |
| `edge_id` | `VARCHAR(50)` | SUMO 道路 edge ID。 |
| `spot_type` | `spot_category` | `on-street` または `off-street`。 |
| `capacity` | `INT` | 駐車容量。 |
| `occupied` | `INT` | 現在の占有または予約数。 |
| `base_price` | `DECIMAL(5,2)` | 基本価格。 |
| `current_price` | `DECIMAL(5,2)` | シナリオ B で更新される動的価格。 |

### 4.3 テーブル: `Cruising_Logs`

車両ごとの駐車探索結果を保存します。

| フィールド | 型 | 説明 |
| --- | --- | --- |
| `log_id` | `SERIAL` | 主キー。 |
| `vehicle_id` | `VARCHAR(50)` | SUMO 車両 ID。 |
| `scenario` | `VARCHAR(20)` | `Baseline` または `Smart_Booking_Priced` などのシナリオ名。 |
| `search_time_sec` | `FLOAT` | 車両出発から駐車または失敗までの時間。 |
| `cruising_distance_m` | `FLOAT` | 探索巡航距離。予約方式のシナリオ B は 0 を記録します。 |
| `final_spot_id` | `VARCHAR(50)` | 最終駐車スペース。失敗または車両消失時は `NULL`。 |
| `created_at` | `TIMESTAMP` | 記録時刻。 |
| `total_fuel_mg` | `FLOAT` | 探索中の累積燃料消費。 |

### 4.4 テーブル: `Simulation_Runs`

シナリオ実行ごとの全体サマリーを保存します。ダッシュボードはこのテーブルを使い、全車両の駐車完了に必要なシミュレーション時間を比較します。

| フィールド | 型 | 説明 |
| --- | --- | --- |
| `run_id` | `SERIAL` | 主キー。 |
| `scenario` | `VARCHAR(20)` | シナリオ名。 |
| `completion_time_sec` | `FLOAT` | 処理済み全車両の駐車完了に必要な全体シミュレーション時間。 |
| `total_vehicles` | `INT` | その実行で処理した車両数。 |
| `parked_vehicles` | `INT` | 駐車に成功した車両数。 |
| `failed_vehicles` | `INT` | 失敗または消失した車両数。 |
| `parking_rate` | `FLOAT` | `parked_vehicles / total_vehicles` で計算される駐車率。 |
| `created_at` | `TIMESTAMP` | サマリー記録時刻。 |

---

## 5. プロジェクト構成

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
│   ├── cbd.poly.xml          # SUMO ポリゴン/領域補助ファイル
│   ├── demo.sumocfg          # SUMO メイン設定
│   ├── demo.net.xml          # 道路網
│   ├── demo.rou.xml          # 車両ルート
│   ├── demo.trips.xml        # OD 需要
│   ├── gui-settings.xml      # SUMO-GUI 表示設定
│   ├── parking.add.xml       # 駐車エリア定義
│   └── schema.sql            # DB スキーマと初期駐車データ
├── scripts/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py         # グローバル設定、SUMO コマンド、シミュレーションパラメータ
│   │   ├── connection.py     # PostgreSQL 接続
│   │   ├── db_ops.py         # ログ、実行サマリー、駐車状態同期
│   │   ├── gui_tracker.py    # SUMO-GUI カメラ追跡
│   │   ├── monitor.py        # matplotlib リアルタイムモニター
│   │   ├── parking_logic.py  # シナリオ A 路上探索ロジック
│   │   ├── recording.py      # ffmpeg 録画とウィンドウ配置
│   │   └── reset_db.py       # DB リセット補助
│   ├── generate_network.ps1  # 道路網生成
│   ├── generate_parking.py   # 駐車 XML と SQL 生成
│   ├── generate_traffic.py   # 交通需要生成
│   ├── init_db.py            # DB 初期化
│   ├── prepare_simulation.py # 一括準備スクリプト
│   ├── run_dashboard.py      # Streamlit ダッシュボード
│   ├── run_scenario_A_baseline.py # シナリオ A メインプログラム
│   └── run_scenario_B_smart.py    # シナリオ B メインプログラム
└── recordings/               # ローカル録画出力、コミット対象外
```

---

## 6. 主要設定

主要パラメータは `scripts/core/config.py` にあります。

| パラメータ | 既定値 | 用途 |
| --- | --- | --- |
| `CONFIG_DIR` | `configs/` | SUMO と SQL の設定ディレクトリ。 |
| `HAS_GUI` | `True` | `sumo-gui` または headless `sumo` の選択。 |
| `SIMULATION_DURATION_LIMIT` | `7200` | 最大シミュレーション時間、秒。 |
| `TOTAL_VEHICLES_TARGET` | `2500` | 目標車両数。 |
| `PARKING_DURATION` | `7200` | 駐車停止時間。 |
| `SIGHT_DISTANCE` | `180.0` | シナリオ A の可視探索距離。 |
| `SPOT_STOP_MARGIN` | `3.0` | 停止可能な最小前方距離。 |
| `INTERSECTION_LOOKAHEAD` | `40.0` | 交差点の先読み距離。 |
| `TARGET_TIMEOUT` | `120` | 目標駐車スペース固定後のタイムアウト。 |
| `PLOTTER_UPDATE_INTERVAL` | `5` | matplotlib 更新間隔。 |
| `DB_SYNC_INTERVAL` | `60` | データベース同期間隔。 |
| `WEIGHT_DISTANCE` | `1.0` | シナリオ B コスト関数の距離重み。 |
| `WEIGHT_PRICE` | `100.0` | シナリオ B コスト関数の価格重み。 |

---

## 7. モジュールと関数

### 7.1 `scripts/core/connection.py`

| 関数 | 機能 |
| --- | --- |
| `get_db_config()` | `.env` または環境変数から PostgreSQL 接続設定を読み取ります。 |
| `get_db_connection()` | `psycopg2` 接続オブジェクトを作成して返します。 |

### 7.2 `scripts/core/db_ops.py`

| 関数 | 機能 |
| --- | --- |
| `ensure_simulation_runs_table(cursor)` | `Simulation_Runs` 実行サマリーテーブルが存在することを保証します。 |
| `log_cruise()` | 車両探索結果を 1 件 `Cruising_Logs` に挿入します。 |
| `log_run_summary()` | シナリオ単位の実行サマリーを `Simulation_Runs` に挿入します。 |
| `sync_spots()` | シナリオ A の `occupied` 状態を `Parking_Spots` に一括反映します。 |
| `sync_spots_priced()` | シナリオ B の `occupied` と `current_price` を一括反映します。 |

### 7.3 `scripts/core/parking_logic.py`

| 関数 | 機能 |
| --- | --- |
| `reroute_random()` | 現在 edge、反対 edge、隣接 edge を避けて新しい目標 edge を選択します。 |
| `scan_street()` | 位置、可視距離、交差点先読み、占有状態を使って候補空きスペースを探索します。 |
| `try_park()` | 現在 edge では `setParkingAreaStop` を呼び、別 edge では pending 状態として経路変更します。 |
| `check_pending()` | pending スペースの edge に到達した車両に対して実際の駐車を試みます。 |
| `handle_occupied()` | 無効、満車、通過済みの目標スペースを取り消し、車両を再ルーティングします。 |

### 7.4 `scripts/core/gui_tracker.py`

| クラス / メソッド | 機能 |
| --- | --- |
| `GUITracker` | SUMO-GUI の車両カメラ追跡を管理します。 |
| `update(active_vehicles, veh_stats, current_time)` | 追跡車両を選択または維持し、SUMO-GUI カメラを更新します。 |
| `current_protagonist` | 現在追跡中の車両 ID を返します。 |
| `on_vehicle_parked(vid)` | 追跡車両が駐車した後、追跡対象を解除します。 |

### 7.5 `scripts/core/monitor.py`

| クラス / 関数 | 機能 |
| --- | --- |
| `MultiprocessingPlotter` | 別プロセスでリアルタイム matplotlib グラフを描画します。 |
| `send_data(step, veh_stats)` | 車両状態から駐車数、平均時間、燃料、速度などの指標を抽出します。 |
| `close()` | 描画プロセスに停止信号を送り、終了を待ちます。 |
| `_render_full()` | シナリオ A 用 6 パネルモニター。 |
| `_render_compact()` | シナリオ B 用 4 パネルモニター。 |

### 7.6 `scripts/core/recording.py`

| クラス / 関数 | 機能 |
| --- | --- |
| `place_sumo_left_half()` | Windows で SUMO-GUI を画面左半分へ移動します。 |
| `ScreenRecorder.start()` | ffmpeg `gdigrab` でデスクトップ録画を開始します。 |
| `ScreenRecorder.stop()` | ffmpeg を正常停止し、中断された実行でも動画生成をできるだけ保証します。 |
| `prepare_visual_session()` | ウィンドウ配置、録画開始、プリロール待機を行います。 |

### 7.7 `scripts/core/reset_db.py`

| 関数 | 機能 |
| --- | --- |
| `reset_database(clear_logs=False, scenario_to_clear=None)` | 駐車占有と価格を初期化し、全ログまたは指定シナリオログを選択的に削除します。 |

### 7.8 `scripts/run_scenario_A_baseline.py`

| 関数 | 機能 |
| --- | --- |
| `_load_spots()` | DB と `parking.add.xml` から容量、edge、開始位置を読み込みます。 |
| `_load_edges()` | `demo.net.xml` から edge 端点、ノード、長さを抽出します。 |
| `_build_opposite_map()` | 反対 edge の参照テーブルを作成します。 |
| `_build_outgoing_map()` | 下流 edge の参照テーブルを作成します。 |
| `_spots_by_edge()` | 高速探索のため駐車スペースを edge ごとにグループ化します。 |
| `_init_stats()` | 車両ごとの状態を初期化します。 |
| `_settle()` | 駐車成功結果を記録します。 |
| `_settle_lost()` | 失敗または消失車両を記録します。 |
| `_process_vehicle()` | シナリオ A の単一車両について指標、探索、駐車、タイムアウト、再ルーティングを処理します。 |
| `run_baseline()` | シナリオ A のメイン入口です。 |

### 7.9 `scripts/run_scenario_B_smart.py`

| 関数 | 機能 |
| --- | --- |
| `_load_spots()` | DB から駐車容量、価格、edge 情報を読み込みます。 |
| `_compute_positions()` | TraCI 起動後に駐車スペースの edge 座標を計算します。 |
| `_build_pricing_index()` | 反復集計を減らすため、路上駐車グループと路外駐車場インデックスを事前計算します。 |
| `_price_from_rate()` | 占有率に応じて基本価格、1.5 倍、2 倍価格を返します。 |
| `_compute_pricing()` | 占有率 70% 超で 1.5 倍、90% 超で 2 倍に価格更新します。 |
| `_find_best_spot()` | 距離と価格に基づいて最小コストの駐車スペースを選択します。 |
| `_assign_vehicle()` | 目標 edge、駐車停止コマンド、初期車両状態を設定します。 |
| `_settle()` | 車両結果を `Cruising_Logs` に記録します。 |
| `_handle_departed()` | 新規出発車両に駐車スペースを割り当てます。 |
| `_process_driving()` | 走行車両を更新し、駐車成功または車両消失を検出します。 |
| `run_smart_booking_with_pricing()` | シナリオ B のメイン入口です。 |

### 7.10 その他のスクリプト

| スクリプト / 関数 | 機能 |
| --- | --- |
| `scripts/init_db.py::init_database()` | `configs/schema.sql` を読み込んで実行します。 |
| `scripts/prepare_simulation.py::run_step()` | 単一準備ステップを実行し、終了コードを確認します。 |
| `scripts/prepare_simulation.py::main()` | 道路網、駐車、交通、データベース準備を順に実行します。 |
| `scripts/run_dashboard.py::fetch_data()` | Streamlit 用のシナリオ指標を `Cruising_Logs` と `Simulation_Runs` から集計します。 |

---

## 8. 指標の扱い

本プロジェクトでは、データベースに実際に記録された指標のみを報告対象にします。

- 駐車成功数: `final_spot_id IS NOT NULL`
- 失敗または消失数: `final_spot_id IS NULL`
- 平均探索時間: `AVG(search_time_sec)`
- 全車両駐車完了時間: `Simulation_Runs.completion_time_sec`
- 駐車率: `Simulation_Runs.parking_rate`
- 総燃料消費: `SUM(total_fuel_mg)`
- シナリオ A 巡航距離: `SUM(cruising_distance_m)`

現在は両シナリオとも 100% の駐車率に達するため、レポートとダッシュボードでは成功率を主要比較指標として扱いません。主な比較対象は、全車両の駐車完了に必要な全体シミュレーション時間です。

収集されていない、またはデータベースに書き込まれていない指標を、レポート、論文、ダッシュボードで実測結果として扱うべきではありません。
