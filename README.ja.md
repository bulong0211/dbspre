<h1 align="center">ITS スマート駐車割り当てと巡航削減シミュレーションシステム</h1>

<p align="center">
  <em>インテリジェント駐車予約・動的価格設定シミュレーションシステム</em>
</p>

<p align="center">
    <img src="https://img.shields.io/badge/Python-3.10-blue.svg" alt="Python Version">
    <img src="https://img.shields.io/badge/SUMO-Simulation-orange.svg" alt="SUMO">
    <img src="https://img.shields.io/badge/Database-PostgreSQL-blue.svg" alt="PostgreSQL">
</p>

> **多言語ドキュメント | Multilingual Documentation:** [English](README.en.md) | [中文](README.md) | [한국어](README.ko.md) | 日本語

---

## 目次

- [プロジェクト概要](#プロジェクト概要)
- [データベース設計](#データベース設計)
- [プロジェクト構造](#プロジェクト構造)
- [クイックスタート](#クイックスタート)
- [ソフトウェア操作方法](#ソフトウェア操作方法)
- [モジュールリファレンス](#モジュールリファレンス)

---

## プロジェクト概要

本プロジェクトは、**SUMO**（Simulation of Urban MObility）ミクロ交通シミュレーションと **PostgreSQL** リアルタイム予約データベースを組み合わせ、中心業務地区（CBD）における都市の**駐車巡航問題**（cruising-for-parking）に対処します。

**2つのシナリオを比較：**

| シナリオ | 説明 |
|----------|-------------|
| **A — ベースライン** | 車両が予約システムなしで道路網全体を盲目的に巡航し、空き駐車スペースを探索します。 |
| **B — スマート予約と価格設定** | 車両生成時に距離と動的サージ価格を組み合わせたコスト関数により最適な駐車スペースが割り当てられます。 |

**主要機能：**

- **駐車スキーマ** — SUMO駐車エリアをリレーショナルデータベースにマッピングし、リアルタイム状態追跡。
- **巡航検出** — TraCIを通じて各車両を監視し、探索時間、走行距離、燃料消費量を記録。
- **予約エンジン** — SQL状態クエリに基づき、新規進入車両に利用可能な駐車スペースを割り当て予約。
- **動的価格設定** — サージ価格を実装：占有率70%超で基本料金の1.5倍、90%超で2倍。
- **パフォーマンスダッシュボード** — StreamlitベースのWebダッシュボードで両シナリオの主要指標を比較。

---

## データベース設計

システムはリアルタイム状態同期に **PostgreSQL** を使用します。接続パラメータはプロジェクトルートの `.env` ファイルで設定します。スキーマは `scripts/generate_parking.py` によって自動生成され `configs/schema.sql` に書き込まれます。

### テーブル: `Parking_Spots`（駐車スペース状態）

オフストリートとオンストリートの全駐車スペースのリアルタイム状態を記録します。

| カラム | 型 | 説明 |
|--------|------|-------------|
| `spot_id` | `VARCHAR(50)` | 主キー；一意の駐車スペース識別子（例: `off_street_0`, `on_street_42`） |
| `edge_id` | `VARCHAR(50)` | 駐車スペースが属する道路セグメント（edge） |
| `spot_type` | `ENUM('on-street', 'off-street')` | カテゴリ：路上駐車 または 駐車場 |
| `capacity` | `INT` | 収容可能な最大車両数 |
| `occupied` | `INT` | 現在占有/予約済み数（デフォルト0） |
| `base_price` | `DECIMAL(5,2)` | 基本駐車料金 |
| `current_price` | `DECIMAL(5,2)` | サージ調整駐車料金（シナリオBでリアルタイム更新） |

### テーブル: `Cruising_Logs`（巡航ログ）

各車両の駐車探索ライフサイクルと環境コストを記録します。

| カラム | 型 | 説明 |
|--------|------|-------------|
| `log_id` | `SERIAL` | 主キー；自動採番 |
| `vehicle_id` | `VARCHAR(50)` | 車両識別子 |
| `scenario` | `VARCHAR(20)` | シナリオ名（`Baseline` または `Smart_Booking_Priced`） |
| `search_time_sec` | `FLOAT` | 駐車探索に費やした時間（秒） |
| `cruising_distance_m` | `FLOAT` | 探索中の総走行距離（メートル） |
| `final_spot_id` | `VARCHAR(50)` | 最終的に駐車したスペース（失敗時はNULL） |
| `total_fuel_mg` | `FLOAT` | 探索中に消費した総燃料（ミリグラム） |
| `created_at` | `TIMESTAMP` | 自動生成ログタイムスタンプ |

---

## プロジェクト構造

```text
dbspre/
├── configs/                          # SUMO設定ファイルとSQLスキーマ
│   ├── demo.net.xml                  # 15×15グリッド道路網
│   ├── demo.rou.xml                  # 車両ルート設定
│   ├── demo.sumocfg                  # SUMO統合起動設定
│   ├── demo.trips.xml                # 車両トリップの発着地
│   ├── gui-settings.xml              # SUMO GUI表示設定
│   ├── parking.add.xml               # 駐車場のジオメトリとスペース配置
│   └── schema.sql                    # データベースDDLと初期データ
├── scripts/                          # Pythonスクリプト
│   ├── core/                         # 共有コアモジュール
│   │   ├── __init__.py               # パッケージマーカー
│   │   ├── config.py                 # シミュレーション定数とパス
│   │   ├── connection.py             # PostgreSQL接続ファクトリ
│   │   ├── db_ops.py                 # データベースCRUD操作
│   │   ├── gui_tracker.py            # SUMO-GUIカメラ追跡ロジック
│   │   ├── monitor.py                # リアルタイムmatplotlibプロットエージェント
│   │   ├── parking_logic.py          # 道路レベル駐車探索ロジック（シナリオA）
│   │   └── reset_db.py               # データベース状態リセットユーティリティ
│   ├── generate_network.ps1          # PowerShell: netgenerateでグリッドネットワーク生成
│   ├── generate_parking.py           # 駐車場と路上スペース生成（XML + SQL）
│   ├── generate_traffic.py           # CBD方面の通勤トリップ2,500台を生成
│   ├── init_db.py                    # schema.sqlを実行してデータベースを初期化
│   ├── prepare_simulation.py         # ワンクリック準備: ネットワーク→駐車→交通→DB初期化
│   ├── run_dashboard.py              # Streamlitパフォーマンス比較ダッシュボード
│   ├── run_scenario_A_baseline.py    # シナリオA: ブラインド巡航（予約なし）
│   └── run_scenario_B_smart.py       # シナリオB: 動的価格設定スマート予約
├── .env.example                      # データベース接続テンプレート
├── requirements.txt                  # Python依存関係リスト
└── README.md                         # このドキュメント
```

---

## クイックスタート

### 前提条件

- **Python 3.10**（仮想環境管理に `uv` の使用を推奨）
- **PostgreSQL** ローカルまたはリモートで実行中
- **SUMO**（Simulation of Urban MObility）インストール済み、システム `PATH` に追加、`SUMO_HOME` 環境変数設定済み
- **VS Code**（推奨）。Pylanceサポートのため `.vscode/settings.json` に以下を追加：

```json
{
    "python.analysis.extraPaths": ["${workspaceFolder}/scripts"]
}
```

### 1. クローンと依存関係のインストール

```bash
git clone https://github.com/bulong0211/dbspre.git
cd dbspre

# uvを使用（推奨）
uv sync

# またはpipを使用
pip install -r requirements.txt
```

### 2. データベース設定

環境テンプレートをコピーし、PostgreSQL認証情報を入力してください：

```bash
cp .env.example .env
```

`.env` を編集：

```env
DB_NAME=smart_parking
DB_USER=postgres
DB_PASSWORD=your_password_here
DB_HOST=localhost
DB_PORT=5432
```

> **注意:** 最初にPostgreSQLでデータベースを作成してください（例: `CREATE DATABASE smart_parking;`）。

### 3. シミュレーション環境の準備

`configs/` にネットワークファイルと駐車ファイルが既に存在する場合は、この手順をスキップしてください。それ以外の場合は、ワンクリック準備スクリプトを実行してください：

```bash
uv run scripts/prepare_simulation.py
```

ネットワーク生成 → 駐車生成 → 交通生成 → データベース初期化を順次実行します。

### 4. シミュレーションの実行

```bash
# シナリオA — ベースライン（ブラインド巡航、起動時に全履歴ログをクリア）
uv run scripts/run_scenario_A_baseline.py

# シナリオB — スマート予約と動的価格設定
uv run scripts/run_scenario_B_smart.py
```

各シミュレーションは最大7,200秒（2時間）、または2,500台の車両がすべて処理されるまで実行されます。リアルタイム指標がmatplotlibウィンドウに表示され、結果はPostgreSQLに書き込まれます。

### 5. ダッシュボードの表示

Streamlitパフォーマンス比較ダッシュボードを起動：

```bash
uv run streamlit run scripts/run_dashboard.py
```

ブラウザで `http://localhost:8501` を開き、両シナリオの成功率、探索時間、燃料消費量、巡航距離を比較します。

---

## ソフトウェア操作方法

### シミュレーションフロー

両シナリオとも、TraCIを通じてSUMOと統合された同じ高レベルループに従います：

```
1. データベース状態をリセット
2. PostgreSQLに接続
3. 駐車スペースデータをロード
4. デモ設定でSUMOを起動
5. シミュレーションにアクティブ車両が存在し、時間が7200秒未満の間：
   a. シミュレーションを1ステップ進める
   b. GUIカメラ追跡を更新
   c. 新規出発車両を処理（駐車スペース割り当て/ルート設定）
   d. 走行中のアクティブ車両を処理（指標更新、駐車検出、タイムアウト処理）
   e. リアルタイムプロッタを更新
   f. 早期完了をチェック（2,500台すべて処理）
   g. 60秒ごとに駐車スペース占有率と価格をデータベースに同期
6. 最終データベース同期
7. SUMO、プロッタ、データベース接続を閉じる
```

### シナリオ間の主な違い

| 側面 | シナリオA | シナリオB |
|--------|-----------|-----------|
| 駐車スペース割り当て | なし（車両が道路スキャンで探索） | 生成時にコスト関数で最適スペースを割り当て |
| ナビゲーション | ランダムedge再ルーティング | 割り当てスペースへの直接ルート |
| 動的価格設定 | 未使用 | 毎ステップサージ価格を更新 |
| 運転挙動 | `setSpeedFactor(0.4)`, `setImperfection(0.9)` | 同一パラメータ |
| タイムアウト | 120秒ターゲットタイムアウト後再ルーティング | 120秒ターゲットタイムアウト後テレポート |
| 駐車ロジック | `parking_logic.py`（スキャン、try_park、再ルーティング） | `changeTarget` + `setParkingAreaStop` |

---

## モジュールリファレンス

### `core/config.py` — 設定定数とパス

調整可能なすべてのシミュレーションパラメータを定義します。

| 定数 | 値 | 説明 |
|----------|-------|-------------|
| `CONFIG_DIR` | `Path(...)/configs` | SUMO設定ファイルのパス |
| `SIMULATION_DURATION_LIMIT` | `7200` | 最大シミュレーション時間（秒） |
| `TOTAL_VEHICLES_TARGET` | `2500` | 処理する総車両数 |
| `SIGHT_DISTANCE` | `80.0` | 道路スキャンの前方視認距離（メートル） |
| `TARGET_TIMEOUT` | `120` | 放棄前に駐車スペースに固定される最大秒数 |
| `DB_SYNC_INTERVAL` | `60` | データベース同期間隔（秒） |
| `SCENARIO_A_NAME` | `"Baseline"` | データベース内のシナリオA識別子 |
| `SCENARIO_B_NAME` | `"Smart_Booking_Priced"` | データベース内のシナリオB識別子 |
| `WEIGHT_DISTANCE` | `1.0` | コスト関数における距離の重み（シナリオB） |
| `WEIGHT_PRICE` | `100.0` | コスト関数における価格の重み（シナリオB） |

---

### `core/connection.py` — データベース接続ファクトリ

| 関数 | 説明 |
|----------|-------------|
| `get_db_config()` | 環境変数（`.env`）からデータベース接続パラメータを読み取ります。`dbname`, `user`, `password`, `host`, `port` キーを持つ辞書を返します。 |
| `get_db_connection()` | `get_db_config()` を使用して `psycopg2` 接続オブジェクトを作成し返します。 |

---

### `core/db_ops.py` — データベース操作

| 関数 | シグネチャ | 説明 |
|----------|-----------|-------------|
| `log_cruise()` | `(cursor, vid, scenario, search_time, cruise_dist, total_fuel, spot_id)` | 車両の探索結果を記録する行を `Cruising_Logs` に挿入します。 |
| `sync_spots()` | `(cursor, conn, spots_data)` | 全駐車スペースの `Parking_Spots.occupied` を一括更新します。シナリオAで使用。 |
| `sync_spots_priced()` | `(cursor, conn, spots_data)` | 全駐車スペースの `occupied` と `current_price` の両方を一括更新します。シナリオBで使用。 |

---

### `core/gui_tracker.py` — SUMO-GUIカメラ追跡

ランダムに選択された「主人公」車両を追跡するSUMO-GUIカメラを管理し、駐車探索の一人称視点を提供します。

| クラス | 説明 |
|-------|-------------|
| `GUITracker` | 現在の主人公車両を追跡し、設定可能なクールダウンでカメラ切り替えを管理します。 |

| メソッド | 説明 |
|--------|-------------|
| `__init__()` | トラッカー状態を初期化: `protagonist=None`, `total_tracked=0`, `last_track_time=0.0`. |
| `update(active_vehicles, veh_stats, current_time)` | 毎ステップ呼び出されます。現在の主人公が失われた場合、新しい主人公を選択します。SUMOが内部状態を失った場合、追跡を再適用します。`GUI_REFRESH_INTERVAL` で間引き。 |
| `on_vehicle_parked(vid)` | 主人公が正常に駐車した場合、主人公をクリアします。 |

| プロパティ | 説明 |
|----------|-------------|
| `current_protagonist` | 現在追跡中の車両ID（または `None`）を返します。 |

---

### `core/monitor.py` — リアルタイムプロットエージェント

別プロセスでmatplotlibを使用してシミュレーション指標のリアルタイム可視化を提供します。

| クラス | 説明 |
|-------|-------------|
| `MultiprocessingPlotter` | 車両統計から指標を抽出し、`multiprocessing.Queue` を介してバックグラウンドレンダリングプロセスに送信するメインプロセスプロキシ。 |

| メソッド | 説明 |
|--------|-------------|
| `__init__(window_title, layout="A")` | レンダラーサブプロセスを開始。`layout="A"` は6チャート（巡航指標含む）、`layout="B"` は4チャート（駐車数、探索時間、燃料、速度）を表示。 |
| `send_data(step, veh_stats)` | 現在の指標（アクティブ数、駐車数、平均探索時間、総燃料、平均速度）を計算しレンダーキューにプッシュ。 |
| `close()` | `STOP` シグナルを送信し、レンダラープロセスを終了。 |

---

### `core/parking_logic.py` — 道路レベル駐車探索（シナリオA）

実際の運転者が道路や交差点をスキャンして空き駐車スペースを探す様子をシミュレートします。中核原則：SUMOの `setParkingAreaStop` が駐車可否の唯一の判断基準です。

| 関数 | シグネチャ | 説明 |
|----------|-----------|-------------|
| `reroute_random()` | `(vid, all_edges, opposite_map, outgoing_map)` | 現在のedge、反対側のedge、隣接するedgeを除外したランダムなedgeを新しい目的地として割り当てます。失敗時は `False` を返します。 |
| `scan_street()` | `(vid, current_edge, current_lanepos, spots_by_edge, all_spots, opposite_map, outgoing_map, edge_lengths, full_scan)` | 現在の道路（およびオプションで交差方向と次のルートedge）を視認距離内でスキャンし空きスペースを探します。`(spot_id, spot_edge)` または `(None, None)` を返します。 |
| `try_park()` | `(vid, spot_id, spot_edge, stats, current_edge, all_spots)` | 発見したスペースへの駐車を試みます。同じedge：`setParkingAreaStop` を呼出。異なるedge：`changeTarget` を呼出し保留中の予約を記録。既に確定済みの場合は新規スペースを拒否。成功時 `True` を返します。 |
| `check_pending()` | `(vid, stats, current_edge, all_spots, all_edges, opposite_map, outgoing_map)` | 保留中のスペースがあるedgeに車両が到着したら駐車を確定しようと試みます。スペースが占有済みになった場合はクリーンアップ。 |
| `handle_occupied()` | `(vid, stats, current_edge, all_spots, all_edges, opposite_map, outgoing_map)` | ターゲットスペースが占有されたか、車両がターゲット道路を離れたことを検出。スペースを解放し再ルーティングをトリガー。 |

---

### `core/reset_db.py` — データベース状態リセット

| 関数 | シグネチャ | 説明 |
|----------|-----------|-------------|
| `reset_database()` | `(clear_logs=False, scenario_to_clear=None)` | `Parking_Spots.occupied` を0に、`current_price` を `base_price` にリセット。`clear_logs=True` の場合 `Cruising_Logs` を切り詰め。`scenario_to_clear` が指定された場合、そのシナリオのログのみ削除。 |

---

### `run_scenario_A_baseline.py` — シナリオA: ブラインド巡航

車両が予約システムなしでランダムな目的地を割り当てられ、道路をスキャンして空き駐車スペースを探すベースラインシナリオを実装します。

**内部関数:**

| 関数 | 説明 |
|----------|-------------|
| `_load_spots(cursor)` | データベースから駐車スペースメタデータをロードし、`parking.add.xml` を解析して幾何データ（`startPos`, `lane`）を取得。 |
| `_load_edges()` | `demo.net.xml` を解析し、from/toノード座標と計算長を持つ道路edge辞書を構築。 |
| `_init_stats(current_time)` | 新規生成車両の初期統計辞書を作成。 |
| `_settle(vid, stats, current_time, current_dist, spot_id, cursor, conn)` | 正常に駐車した車両の結果をデータベースに記録。 |
| `_settle_lost(vid, stats, current_time, cursor, conn)` | テレポート/消失した車両の結果を `final_spot_id = NULL` で記録。 |
| `_process_vehicle(...)` | 単一巡航車両のステップ単位状態マシン：駐車状態確認、保留スペース処理、道路スキャン、駐車試行、必要時再ルーティング。 |
| `run_baseline()` | メインエントリポイント。シミュレーションライフサイクル全体を統括。 |

---

### `run_scenario_B_smart.py` — シナリオB: スマート予約と動的価格設定

車両生成時にコスト関数で最適駐車スペースを割り当て、リアルタイム占有率に基づき価格が動的に調整されるインテリジェントシナリオを実装します。

**内部関数:**

| 関数 | 説明 |
|----------|-------------|
| `_load_spots(cursor)` | データベースから価格情報付きの駐車スペースデータをロード。 |
| `_compute_positions(all_spots)` | 各駐車スペースレーンの物理座標を取得（TraCI実行中必須）。 |
| `_compute_pricing(all_spots)` | 毎シミュレーションステップでサージ価格を計算。小規模路上スペース（容量≤3）は道路ごとに集計して占有率を計算。価格段階：>90% → 2倍、>70% → 1.5倍、その他基本。 |
| `_find_best_spot(vehicle_pos, all_spots)` | `cost = 距離 × WEIGHT_DISTANCE + 現在価格 × WEIGHT_PRICE` を最小化して最適駐車スペースを選択。利用可能容量のあるスペースのみ考慮。 |
| `_assign_vehicle(vid, spot_id, all_spots, veh_stats, current_time)` | `changeTarget` と `setParkingAreaStop` で車両を割当スペースにルーティング。全TraCI呼出成功後にのみ予約カウンタを増加（原子性）。 |
| `_settle(vid, stats, current_time, spot_id, cursor, conn)` | 車両結果を `Cruising_Logs` テーブルに記録。 |
| `_handle_departed(departed, all_spots, veh_stats, current_time)` | 新規生成車両を処理：運転パラメータ設定、最適スペース探索・割当。割当失敗時は警告を記録。 |
| `_process_driving(veh_stats, sub_results, current_time, all_spots, cursor, conn, gui)` | 全走行中車両のステップ単位処理：速度/距離/燃料指標更新、テレポート検出、ターゲットタイムアウト強制（停滞車両解放）、駐車成功検出。 |
| `run_smart_booking_with_pricing()` | メインエントリポイント。シミュレーションライフサイクル全体を統括。 |

---

### 補助スクリプト

| スクリプト | 説明 |
|--------|-------------|
| `generate_network.ps1` | SUMOの `netgenerate` を呼び出し15×15 CBDグリッド道路網を生成。 |
| `generate_parking.py` | 道路網を解析し、50箇所のオフストリート駐車場（各38台）と800箇所のオンストリート駐車スペース（各1台）を生成、`parking.add.xml` と `schema.sql` を出力。 |
| `generate_traffic.py` | 境界入口edgeからCBDコアエリア方面への通勤トリップ2,500台を生成、出発時間順にソートし `demo.trips.xml` を出力。 |
| `init_db.py` | PostgreSQLに接続し `schema.sql` を実行してテーブル作成と初期駐車スペースデータ挿入。 |
| `prepare_simulation.py` | ネットワーク生成 → 駐車生成 → 交通生成 → データベース初期化を順次実行するワンクリック準備オーケストレータ。 |
| `run_dashboard.py` | `Cruising_Logs` をクエリし、シナリオA対シナリオBの比較KPIカードとチャート（成功率、探索時間、燃料消費量、巡航距離）をレンダリングするStreamlit Webダッシュボード。 |

| 関数（ダッシュボード） | 説明 |
|----------------------|-------------|
| `fetch_data()` | シナリオ別に集計されたシミュレーション指標をPostgreSQLからクエリ。5秒間キャッシュ。 |
