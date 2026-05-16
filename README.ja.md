<h1 align="center">ITS スマート駐車割り当てと巡航削減シミュレーション</h1>

<p align="center">
  <em>SUMO、TraCI、PostgreSQL、リアルタイム可視化による駐車戦略比較実験プロジェクト</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/SUMO-TraCI-orange.svg" alt="SUMO">
  <img src="https://img.shields.io/badge/Database-PostgreSQL-blue.svg" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Visualization-Matplotlib%20%7C%20Streamlit-green.svg" alt="Visualization">
</p>

> ドキュメント: [中文](README.md) | [English](README.en.md) | [한국어](README.ko.md) | 日本語

---

## 概要

本プロジェクトは **SUMO-GUI** で都市駐車シミュレーションを構築し、**Python TraCI** で車両挙動を制御し、駐車状態と探索結果を **PostgreSQL** に記録します。主な目的は、盲目的な巡航探索とスマート予約方式を、駐車探索時間、成功駐車数、燃料消費、道路網平均速度などの実測指標で比較することです。

現在の実装には 2 つの実験スクリプトがあります。

| スクリプト | シナリオ | 挙動 |
| --- | --- | --- |
| `scripts/run_scenario_A_baseline.py` | シナリオ A: 道路網全体での盲目的探索 | 車両は道路網に入った後、路上の空きスペースを探します。近くに空きがなければ経路変更を繰り返して巡航します。 |
| `scripts/run_scenario_B_smart.py` | シナリオ B: スマート予約 | 車両生成時にデータベースを照会し、距離と動的価格に基づいて利用可能な駐車スペースを予約します。 |

両シナリオのスクリプトは結果を `Cruising_Logs` に書き込み、`Parking_Spots` の占有数と価格フィールドを更新します。`scripts/run_dashboard.py` はデータベースに実際に存在する指標を読み取り、比較ダッシュボードを表示します。

---

## 現在の変更点

- `scripts/core/recording.py` を追加し、SUMO-GUI と matplotlib ウィンドウを自動配置し、必要に応じて ffmpeg 録画を開始します。
- `scripts/core/monitor.py` は matplotlib ウィンドウを画面右半分に配置し、シミュレーションループがまだ進んでいない状態でも応答性を維持します。
- シナリオ A/B スクリプトは `finally` ブロックで録画停止、TraCI 終了、plotter 終了、データベース接続終了を処理します。
- `configs/demo.sumocfg` は、スクリプトがウィンドウ配置と録画プリロールを先に実行できるように、SUMO-GUI を制御可能な状態で開始します。
- `.gitignore` はローカル動画をコミットしないよう `recordings/` を無視します。

---

## プロジェクト構成

```text
dbspre/
├── configs/
│   ├── demo.sumocfg          # SUMO メイン設定
│   ├── demo.net.xml          # 道路網
│   ├── demo.rou.xml          # 車両ルート
│   ├── parking.add.xml       # SUMO 駐車エリア
│   └── schema.sql            # PostgreSQL スキーマと初期駐車データ
├── scripts/
│   ├── core/
│   │   ├── config.py         # グローバルパス、SUMO、DB、録画設定
│   │   ├── db_utils.py       # DB 接続とクリーンアップ
│   │   ├── gui_tracker.py    # SUMO-GUI 車両ハイライトと追跡
│   │   ├── monitor.py        # matplotlib リアルタイムモニター
│   │   ├── parking_logic.py  # 両シナリオ共通の駐車ロジック
│   │   └── recording.py      # ウィンドウ配置と ffmpeg 録画
│   ├── run_scenario_A_baseline.py
│   ├── run_scenario_B_smart.py
│   ├── run_dashboard.py
│   ├── generate_parking.py
│   ├── generate_traffic.py
│   └── prepare_simulation.py
├── recordings/               # ローカル動画出力、git 無視対象
├── pyproject.toml
└── README*.md
```

---

## 要件

- Python 3.10 以上
- `SUMO_HOME` を設定済みの SUMO
- PostgreSQL
- ffmpeg、省略可能。ただし `ENABLE_SCREEN_RECORDING=True` の場合は必要
- 依存関係管理には `uv` を推奨しますが、通常の `pip` も利用できます。

Windows PowerShell 例:

```powershell
$env:SUMO_HOME = "C:\Program Files (x86)\Eclipse\Sumo"
```

プロジェクトルートに `.env` を作成します。

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=parking
DB_USER=postgres
DB_PASSWORD=your_password
```

---

## セットアップ

```powershell
uv sync
```

`uv` を使わない場合:

```powershell
python -m pip install -r requirements.txt
```

シミュレーション資産を生成または更新します。

```powershell
uv run python scripts/prepare_simulation.py
```

シナリオ実行前に PostgreSQL データベースが存在し、`configs/schema.sql` がインポート済みであることを確認してください。

---

## 実行

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

## 可視化と録画

録画は `scripts/core/config.py` で制御します。

```python
ENABLE_SCREEN_RECORDING = True
RECORDING_OUTPUT_DIR = CONFIG_DIR.parent / "recordings"
RECORDING_FPS = 30
RECORDING_PREROLL_SECONDS = 1.0
```

`ENABLE_SCREEN_RECORDING=True` の場合、シナリオ開始順序は次の通りです。

1. シミュレーションを進めずに SUMO-GUI を起動します。
2. matplotlib モニターウィンドウを作成します。
3. SUMO-GUI を画面左半分、matplotlib を右半分に配置します。
4. ffmpeg デスクトップ録画を開始します。
5. `RECORDING_PREROLL_SECONDS` だけ待機します。
6. `traci.simulationStep()` の呼び出しを開始します。
7. シミュレーション終了または早期終了時に `finally` で録画を停止し、リソースを閉じます。

動画ファイルは `recordings/` に保存されます。録画が不要な場合は `ENABLE_SCREEN_RECORDING=False` に設定してください。

---

## データベーステーブル

### `Parking_Spots`

駐車スペースまたは駐車エリアの基本属性とリアルタイム状態を保存します。

| フィールド | 意味 |
| --- | --- |
| `spot_id` | 一意の駐車スペースまたはエリア ID |
| `edge_id` | SUMO 道路セグメント |
| `spot_type` | `on-street` または `off-street` |
| `capacity` | 容量 |
| `occupied` | 現在の占有または予約数 |
| `base_price` | 基本価格 |
| `current_price` | 現在の動的価格 |

### `Cruising_Logs`

各車両が道路網に入ってから駐車成功または失敗に至るまでの結果を保存します。

| フィールド | 意味 |
| --- | --- |
| `vehicle_id` | SUMO 車両 ID |
| `scenario` | 実験シナリオ |
| `search_time_sec` | 駐車探索時間 |
| `cruising_distance_m` | 駐車探索距離 |
| `final_spot_id` | 最終駐車スペース |
| `total_fuel_mg` | 探索中の燃料消費 |
| `created_at` | ログタイムスタンプ |

---

## 主要パラメータ

| パラメータ | 現在の用途 |
| --- | --- |
| `SIGHT_DISTANCE = 180.0` | シナリオ A の路上探索で車両が駐車スペースを確認できる距離しきい値。単位はメートルです。 |
| `DB_SYNC_INTERVAL` | シミュレーション状態をデータベースへ書き戻す間隔です。 |
| `PLOTTER_UPDATE_INTERVAL` | matplotlib モニターの更新頻度です。 |
| `ENABLE_SCREEN_RECORDING` | ffmpeg デスクトップ録画の有効/無効を切り替えます。 |
| `RECORDING_PREROLL_SECONDS` | SUMO のステップ開始前に録画を先行させる時間です。 |

---

## 注意

- レポートとダッシュボードでは、データベースに実際に記録された指標のみを使用してください。
- ffmpeg 録画は現在 Windows `gdigrab` 向けに設定されています。Windows 以外では自動的に録画をスキップします。
- SUMO、PostgreSQL、ffmpeg はローカル環境設定に依存するため、起動問題がある場合は環境変数、データベース接続、PATH を先に確認してください。
