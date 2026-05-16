<h1 align="center">ITS 스마트 주차 할당 및 순항 감소 시뮬레이션</h1>

<p align="center">
  <em>SUMO, TraCI, PostgreSQL, 실시간 시각화를 이용한 주차 전략 비교 실험 프로젝트</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/SUMO-TraCI-orange.svg" alt="SUMO">
  <img src="https://img.shields.io/badge/Database-PostgreSQL-blue.svg" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Visualization-Matplotlib%20%7C%20Streamlit-green.svg" alt="Visualization">
</p>

> 문서: [中文](README.md) | [English](README.en.md) | 한국어 | [日本語](README.ja.md)

---

## 개요

이 프로젝트는 **SUMO-GUI** 기반 도시 주차 시뮬레이션을 구성하고, **Python TraCI**로 차량 동작을 제어하며, 주차 상태와 탐색 결과를 **PostgreSQL**에 기록합니다. 핵심 목적은 맹목적 순항 탐색과 스마트 예약 방식의 차이를 주차 탐색 시간, 성공 주차 수, 연료 소비, 도로망 평균 속도 등 실제 지표로 비교하는 것입니다.

현재 구현은 두 개의 실험 스크립트로 구성됩니다.

| 스크립트 | 시나리오 | 동작 |
| --- | --- | --- |
| `scripts/run_scenario_A_baseline.py` | 시나리오 A: 전체 도로망 맹목 탐색 | 차량은 도로망에 진입한 뒤 도로변 주차 공간을 검색합니다. 가까운 공간이 없으면 계속 경로를 바꾸며 순항합니다. |
| `scripts/run_scenario_B_smart.py` | 시나리오 B: 스마트 예약 | 차량 생성 시 데이터베이스를 조회하고 거리와 동적 가격을 기준으로 사용 가능한 공간을 예약합니다. |

두 시나리오 스크립트는 결과를 `Cruising_Logs`에 기록하고 `Parking_Spots`의 점유 및 가격 필드를 갱신합니다. `scripts/run_dashboard.py`는 데이터베이스에 실제로 존재하는 지표를 읽어 비교 대시보드를 렌더링합니다.

---

## 최근 변경 사항

- `scripts/core/recording.py`를 추가하여 SUMO-GUI와 matplotlib 창을 자동 배치하고 필요 시 ffmpeg 녹화를 시작합니다.
- `scripts/core/monitor.py`는 matplotlib 창을 화면 오른쪽 절반에 배치하며, 시뮬레이션 루프가 아직 진행되지 않아도 창 응답성을 유지합니다.
- 시나리오 A/B 스크립트는 `finally` 블록에서 녹화 중지, TraCI 종료, plotter 종료, 데이터베이스 연결 종료를 처리합니다.
- `configs/demo.sumocfg`는 스크립트가 창 배치와 녹화 예열을 먼저 수행할 수 있도록 SUMO-GUI를 제어 가능한 상태로 시작합니다.
- `.gitignore`는 로컬 영상 파일이 커밋되지 않도록 `recordings/`를 무시합니다.

---

## 프로젝트 구조

```text
dbspre/
├── configs/
│   ├── demo.sumocfg          # SUMO 기본 설정
│   ├── demo.net.xml          # 도로망
│   ├── demo.rou.xml          # 차량 경로
│   ├── parking.add.xml       # SUMO 주차 영역
│   └── schema.sql            # PostgreSQL 스키마 및 초기 주차 데이터
├── scripts/
│   ├── core/
│   │   ├── config.py         # 전역 경로, SUMO, 데이터베이스, 녹화 설정
│   │   ├── db_utils.py       # 데이터베이스 연결 및 정리
│   │   ├── gui_tracker.py    # SUMO-GUI 차량 강조 및 추적
│   │   ├── monitor.py        # matplotlib 실시간 모니터
│   │   ├── parking_logic.py  # 두 시나리오 공통 주차 로직
│   │   └── recording.py      # 창 배치 및 ffmpeg 녹화
│   ├── run_scenario_A_baseline.py
│   ├── run_scenario_B_smart.py
│   ├── run_dashboard.py
│   ├── generate_parking.py
│   ├── generate_traffic.py
│   └── prepare_simulation.py
├── recordings/               # 로컬 영상 출력, git 무시 대상
├── pyproject.toml
└── README*.md
```

---

## 요구 사항

- Python 3.10 이상
- `SUMO_HOME`이 설정된 SUMO
- PostgreSQL
- ffmpeg, 선택 사항이며 `ENABLE_SCREEN_RECORDING=True`일 때만 필요
- 의존성 관리는 `uv`를 권장하지만 일반 `pip`도 사용할 수 있습니다.

Windows PowerShell 예시:

```powershell
$env:SUMO_HOME = "C:\Program Files (x86)\Eclipse\Sumo"
```

프로젝트 루트에 `.env` 파일을 작성합니다.

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=parking
DB_USER=postgres
DB_PASSWORD=your_password
```

---

## 설치 및 준비

```powershell
uv sync
```

`uv`를 사용하지 않는 경우:

```powershell
python -m pip install -r requirements.txt
```

시뮬레이션 자원을 생성하거나 갱신합니다.

```powershell
uv run python scripts/prepare_simulation.py
```

시나리오 실행 전 PostgreSQL 데이터베이스가 존재하고 `configs/schema.sql`이 가져와져 있어야 합니다.

---

## 실행

시나리오 A:

```powershell
uv run python scripts/run_scenario_A_baseline.py
```

시나리오 B:

```powershell
uv run python scripts/run_scenario_B_smart.py
```

대시보드:

```powershell
uv run streamlit run scripts/run_dashboard.py
```

---

## 시각화 및 녹화

녹화는 `scripts/core/config.py`에서 제어합니다.

```python
ENABLE_SCREEN_RECORDING = True
RECORDING_OUTPUT_DIR = CONFIG_DIR.parent / "recordings"
RECORDING_FPS = 30
RECORDING_PREROLL_SECONDS = 1.0
```

`ENABLE_SCREEN_RECORDING=True`일 때 시나리오 시작 순서는 다음과 같습니다.

1. 시뮬레이션을 진행하지 않은 상태로 SUMO-GUI를 시작합니다.
2. matplotlib 모니터 창을 생성합니다.
3. SUMO-GUI를 화면 왼쪽 절반에, matplotlib를 오른쪽 절반에 배치합니다.
4. ffmpeg 데스크톱 녹화를 시작합니다.
5. `RECORDING_PREROLL_SECONDS` 동안 대기합니다.
6. `traci.simulationStep()` 호출을 시작합니다.
7. 시뮬레이션 종료 또는 조기 종료 시 `finally`에서 녹화를 멈추고 자원을 닫습니다.

영상 파일은 `recordings/`에 저장됩니다. 녹화가 필요 없으면 `ENABLE_SCREEN_RECORDING=False`로 설정합니다.

---

## 데이터베이스 테이블

### `Parking_Spots`

주차 공간 또는 주차 영역의 기본 속성과 실시간 상태를 저장합니다.

| 필드 | 의미 |
| --- | --- |
| `spot_id` | 고유 주차 공간 또는 영역 ID |
| `edge_id` | SUMO 도로 세그먼트 |
| `spot_type` | `on-street` 또는 `off-street` |
| `capacity` | 수용량 |
| `occupied` | 현재 점유 또는 예약 수 |
| `base_price` | 기본 가격 |
| `current_price` | 현재 동적 가격 |

### `Cruising_Logs`

각 차량이 도로망에 진입한 뒤 주차 성공 또는 실패까지의 결과를 저장합니다.

| 필드 | 의미 |
| --- | --- |
| `vehicle_id` | SUMO 차량 ID |
| `scenario` | 실험 시나리오 |
| `search_time_sec` | 주차 탐색 시간 |
| `cruising_distance_m` | 주차 탐색 거리 |
| `final_spot_id` | 최종 주차 공간 |
| `total_fuel_mg` | 탐색 중 연료 소비량 |
| `created_at` | 로그 타임스탬프 |

---

## 주요 파라미터

| 파라미터 | 현재 용도 |
| --- | --- |
| `SIGHT_DISTANCE = 180.0` | 시나리오 A 도로변 탐색에서 차량이 주차 공간을 볼 수 있는 거리 임계값, 단위는 미터입니다. |
| `DB_SYNC_INTERVAL` | 시뮬레이션 상태를 데이터베이스에 기록하는 간격입니다. |
| `PLOTTER_UPDATE_INTERVAL` | matplotlib 모니터 갱신 빈도입니다. |
| `ENABLE_SCREEN_RECORDING` | ffmpeg 데스크톱 녹화 사용 여부입니다. |
| `RECORDING_PREROLL_SECONDS` | SUMO 진행 시작 전 녹화 예열 시간입니다. |

---

## 참고

- 보고서와 대시보드는 데이터베이스에 실제로 기록된 지표만 사용해야 합니다.
- ffmpeg 녹화는 현재 Windows `gdigrab` 기준으로 구성되어 있으며, Windows가 아닌 환경에서는 자동으로 건너뜁니다.
- SUMO, PostgreSQL, ffmpeg는 로컬 환경 설정에 의존하므로 시작 문제가 있으면 환경 변수, 데이터베이스 연결, PATH를 먼저 확인하십시오.
