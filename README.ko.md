<h1 align="center">ITS 스마트 주차 할당 및 순항 감소 시뮬레이션</h1>

<p align="center">
  <em>SUMO-GUI, Python TraCI, PostgreSQL, matplotlib, Streamlit 기반 주차 전략 시뮬레이션 소프트웨어</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/SUMO-TraCI-orange.svg" alt="SUMO">
  <img src="https://img.shields.io/badge/Database-PostgreSQL-blue.svg" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Dashboard-Streamlit-green.svg" alt="Streamlit">
</p>

> 문서: [中文](README.md) | [English](README.en.md) | 한국어 | [日本語](README.ja.md)

---

## 1. 프로젝트 개요

이 프로젝트는 도시 주차 탐색 행동이 교통 시스템에 미치는 영향을 분석하기 위한 소프트웨어입니다. SUMO는 도로망과 교통 수요를 생성하고, Python TraCI는 차량을 제어하며, PostgreSQL은 주차 상태와 차량 탐색 로그를 저장합니다. matplotlib는 실시간 모니터링을 제공하고 Streamlit은 실험 결과 비교 대시보드를 제공합니다.

비교 가능한 두 가지 시나리오가 포함됩니다.

| 시나리오 | 실행 스크립트 | 핵심 로직 |
| --- | --- | --- |
| 시나리오 A: 기준 맹목 탐색 | `scripts/run_scenario_A_baseline.py` | 차량은 전체 주차 상태를 알지 못하고 가시 거리 안의 도로변 주차 공간만 탐색합니다. 공간이 없으면 계속 경로를 바꿉니다. |
| 시나리오 B: 스마트 예약 및 동적 가격 | `scripts/run_scenario_B_smart.py` | 차량 출발 시 데이터베이스를 조회하고 거리와 현재 가격을 기준으로 사용 가능한 공간을 선택해 예약합니다. |

현재 실험에서는 두 시나리오 모두 2시간 시뮬레이션 제한 안에 모든 차량의 주차를 완료하며, 주차율은 모두 100%입니다. 따라서 주차율은 사실로만 제시하고, 핵심 비교 지표는 모든 차량의 주차 완료에 필요한 전역 시뮬레이션 시간입니다.

---

## 2. 소프트웨어 실행 방법

### 2.1 요구 사항

- Python 3.10 이상
- `SUMO_HOME`이 설정된 SUMO
- PostgreSQL
- ffmpeg, 선택 사항이며 녹화가 켜져 있을 때만 필요
- 의존성 관리는 `uv` 권장

PowerShell 예:

```powershell
$env:SUMO_HOME = "C:\Program Files (x86)\Eclipse\Sumo"
```

### 2.2 데이터베이스 설정

프로젝트 루트에 `.env`를 작성합니다.

```env
DB_NAME=smart_parking
DB_USER=postgres
DB_PASSWORD=123456
DB_HOST=localhost
DB_PORT=5432
```

`scripts/core/connection.py`가 이 값을 읽습니다. 값이 없으면 위 기본값을 사용합니다. 초기화 스크립트 실행 전 데이터베이스를 생성해야 합니다.

```sql
CREATE DATABASE smart_parking;
```

### 2.3 의존성 설치

```powershell
uv sync
```

`uv`를 쓰지 않는 경우:

```powershell
python -m pip install -r requirements.txt
```

### 2.4 시뮬레이션 자원 생성 및 데이터베이스 초기화

```powershell
uv run python scripts/prepare_simulation.py
```

이 명령은 다음 단계를 실행합니다.

1. `scripts/generate_network.ps1`: SUMO 격자 도로망 생성.
2. `scripts/generate_parking.py`: 주차 XML과 SQL 데이터 생성.
3. `scripts/generate_traffic.py`: 차량 수요 생성.
4. `scripts/init_db.py`: `configs/schema.sql` 실행 및 초기 주차 데이터 삽입.

데이터베이스만 초기화하려면:

```powershell
uv run python scripts/init_db.py
```

### 2.5 실험 실행

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

## 3. 실행 흐름

시나리오 스크립트의 공통 흐름은 다음과 같습니다.

1. 주차 상태를 초기화하고 필요 시 대상 시나리오 로그를 삭제합니다.
2. PostgreSQL에 연결합니다.
3. `Parking_Spots`, SUMO 도로망, 주차 영역 데이터를 로드합니다.
4. SUMO-GUI를 시작합니다.
5. matplotlib 실시간 모니터를 생성합니다.
6. `ENABLE_SCREEN_RECORDING=True`이면 ffmpeg 녹화를 시작합니다.
7. `traci.simulationStep()` 메인 루프에 진입합니다.
8. 출발 차량, 차량 상태, 주차 이벤트, 연료와 거리 지표를 처리합니다.
9. `DB_SYNC_INTERVAL`마다 주차 상태를 PostgreSQL에 동기화합니다.
10. `Simulation_Runs`에 시나리오 실행 요약을 기록합니다. 여기에는 완료 시간, 총 차량 수, 성공 수, 실패 수, 주차율이 포함됩니다.
11. 완료 또는 중단 시 녹화, TraCI, 플로터, 데이터베이스 자원을 닫습니다.

녹화 설정은 `scripts/core/config.py`에 있습니다.

```python
ENABLE_SCREEN_RECORDING = True
RECORDING_OUTPUT_DIR = CONFIG_DIR.parent / "recordings"
RECORDING_FPS = 30
RECORDING_PREROLL_SECONDS = 1.0
```

`recordings/` 디렉터리는 git에서 무시됩니다.

---

## 4. 데이터베이스 설계

데이터베이스 구조는 `configs/schema.sql`에 정의되어 있으며, 하나의 enum 타입과 세 개의 주요 테이블을 포함합니다.

### 4.1 Enum: `spot_category`

```sql
CREATE TYPE spot_category AS ENUM ('on-street', 'off-street');
```

도로변 주차 공간과 노외 주차장을 구분합니다.

### 4.2 테이블: `Parking_Spots`

주차 공간 또는 주차 영역의 정적 속성과 실시간 상태를 저장합니다.

| 필드 | 유형 | 설명 |
| --- | --- | --- |
| `spot_id` | `VARCHAR(50)` | 기본 키, SUMO 주차 영역 ID. |
| `edge_id` | `VARCHAR(50)` | SUMO 도로 edge ID. |
| `spot_type` | `spot_category` | `on-street` 또는 `off-street`. |
| `capacity` | `INT` | 주차 용량. |
| `occupied` | `INT` | 현재 점유 또는 예약 수. |
| `base_price` | `DECIMAL(5,2)` | 기본 가격. |
| `current_price` | `DECIMAL(5,2)` | 시나리오 B에서 갱신되는 동적 가격. |

### 4.3 테이블: `Cruising_Logs`

차량별 주차 탐색 결과를 저장합니다.

| 필드 | 유형 | 설명 |
| --- | --- | --- |
| `log_id` | `SERIAL` | 기본 키. |
| `vehicle_id` | `VARCHAR(50)` | SUMO 차량 ID. |
| `scenario` | `VARCHAR(20)` | `Baseline` 또는 `Smart_Booking_Priced` 같은 시나리오 이름. |
| `search_time_sec` | `FLOAT` | 차량 출발부터 주차 또는 실패까지의 시간. |
| `cruising_distance_m` | `FLOAT` | 탐색 순항 거리. 예약 방식인 시나리오 B는 0을 기록합니다. |
| `final_spot_id` | `VARCHAR(50)` | 최종 주차 공간. 실패 또는 차량 소실 시 `NULL`. |
| `created_at` | `TIMESTAMP` | 기록 시각. |
| `total_fuel_mg` | `FLOAT` | 탐색 중 누적 연료 소비량. |

### 4.4 테이블: `Simulation_Runs`

시나리오 실행별 전역 요약을 저장합니다. 대시보드는 이 테이블을 사용하여 모든 차량의 주차 완료에 필요한 시뮬레이션 시간을 비교합니다.

| 필드 | 유형 | 설명 |
| --- | --- | --- |
| `run_id` | `SERIAL` | 기본 키. |
| `scenario` | `VARCHAR(20)` | 시나리오 이름. |
| `completion_time_sec` | `FLOAT` | 모든 처리 차량의 주차 완료에 필요한 전역 시뮬레이션 시간. |
| `total_vehicles` | `INT` | 해당 실행에서 처리한 차량 수. |
| `parked_vehicles` | `INT` | 성공적으로 주차한 차량 수. |
| `failed_vehicles` | `INT` | 실패 또는 소실 차량 수. |
| `parking_rate` | `FLOAT` | `parked_vehicles / total_vehicles`로 계산한 주차율. |
| `created_at` | `TIMESTAMP` | 요약 기록 시각. |

---

## 5. 프로젝트 구조

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
│   ├── cbd.poly.xml          # SUMO 폴리곤/영역 보조 파일
│   ├── demo.sumocfg          # SUMO 기본 설정
│   ├── demo.net.xml          # 도로망
│   ├── demo.rou.xml          # 차량 경로
│   ├── demo.trips.xml        # OD 수요
│   ├── gui-settings.xml      # SUMO-GUI 표시 설정
│   ├── parking.add.xml       # 주차 영역 정의
│   └── schema.sql            # 데이터베이스 스키마와 초기 주차 데이터
├── scripts/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py         # 전역 설정, SUMO 명령, 시뮬레이션 파라미터
│   │   ├── connection.py     # PostgreSQL 연결
│   │   ├── db_ops.py         # 로그, 실행 요약, 주차 상태 동기화
│   │   ├── gui_tracker.py    # SUMO-GUI 카메라 추적
│   │   ├── monitor.py        # matplotlib 실시간 모니터
│   │   ├── parking_logic.py  # 시나리오 A 도로변 탐색 로직
│   │   ├── recording.py      # ffmpeg 녹화 및 창 배치
│   │   └── reset_db.py       # 데이터베이스 초기화 도구
│   ├── generate_network.ps1  # 도로망 생성
│   ├── generate_parking.py   # 주차 XML 및 SQL 생성
│   ├── generate_traffic.py   # 교통 수요 생성
│   ├── init_db.py            # 데이터베이스 초기화
│   ├── prepare_simulation.py # 일괄 준비 스크립트
│   ├── run_dashboard.py      # Streamlit 대시보드
│   ├── run_scenario_A_baseline.py # 시나리오 A 메인 프로그램
│   └── run_scenario_B_smart.py    # 시나리오 B 메인 프로그램
└── recordings/               # 로컬 녹화 출력, 커밋하지 않음
```

---

## 6. 핵심 설정

주요 파라미터는 `scripts/core/config.py`에 있습니다.

| 파라미터 | 기본값 | 용도 |
| --- | --- | --- |
| `CONFIG_DIR` | `configs/` | SUMO 및 SQL 설정 디렉터리. |
| `HAS_GUI` | `True` | `sumo-gui` 또는 headless `sumo` 사용 여부. |
| `SIMULATION_DURATION_LIMIT` | `7200` | 최대 시뮬레이션 시간(초). |
| `TOTAL_VEHICLES_TARGET` | `2500` | 목표 차량 수. |
| `PARKING_DURATION` | `7200` | 주차 정지 시간. |
| `SIGHT_DISTANCE` | `180.0` | 시나리오 A 가시 탐색 거리. |
| `SPOT_STOP_MARGIN` | `3.0` | 정차 가능 최소 전방 거리. |
| `INTERSECTION_LOOKAHEAD` | `40.0` | 교차로 관찰 거리. |
| `TARGET_TIMEOUT` | `120` | 목표 주차 공간 고정 후 타임아웃. |
| `PLOTTER_UPDATE_INTERVAL` | `5` | matplotlib 갱신 간격. |
| `DB_SYNC_INTERVAL` | `60` | 데이터베이스 동기화 간격. |
| `WEIGHT_DISTANCE` | `1.0` | 시나리오 B 비용 함수의 거리 가중치. |
| `WEIGHT_PRICE` | `100.0` | 시나리오 B 비용 함수의 가격 가중치. |

---

## 7. 모듈 및 함수 설명

### 7.1 `scripts/core/connection.py`

| 함수 | 기능 |
| --- | --- |
| `get_db_config()` | `.env` 또는 환경 변수에서 PostgreSQL 연결 설정을 읽습니다. |
| `get_db_connection()` | `psycopg2` 연결 객체를 생성해 반환합니다. |

### 7.2 `scripts/core/db_ops.py`

| 함수 | 기능 |
| --- | --- |
| `ensure_simulation_runs_table(cursor)` | `Simulation_Runs` 실행 요약 테이블이 존재하는지 보장합니다. |
| `log_cruise()` | 차량 탐색 결과 한 건을 `Cruising_Logs`에 삽입합니다. |
| `log_run_summary()` | 시나리오 단위 실행 요약을 `Simulation_Runs`에 삽입합니다. |
| `sync_spots()` | 시나리오 A의 `occupied` 상태를 `Parking_Spots`에 일괄 반영합니다. |
| `sync_spots_priced()` | 시나리오 B의 `occupied`와 `current_price`를 데이터베이스에 일괄 반영합니다. |

### 7.3 `scripts/core/parking_logic.py`

| 함수 | 기능 |
| --- | --- |
| `reroute_random()` | 현재 edge, 반대 edge, 인접 edge를 피해서 새 목표 edge를 선택합니다. |
| `scan_street()` | 위치, 가시 거리, 교차로 관찰 거리, 점유 상태를 이용해 후보 빈 공간을 탐색합니다. |
| `try_park()` | 현재 edge에서는 `setParkingAreaStop`을 호출하고, 다른 edge에서는 pending 상태로 경로를 변경합니다. |
| `check_pending()` | 차량이 pending 공간의 edge에 도착하면 실제 주차를 시도합니다. |
| `handle_occupied()` | 무효, 만차, 지나친 목표 공간을 취소하고 차량을 재라우팅합니다. |

### 7.4 `scripts/core/gui_tracker.py`

| 클래스 / 메서드 | 기능 |
| --- | --- |
| `GUITracker` | SUMO-GUI 차량 카메라 추적을 관리합니다. |
| `update(active_vehicles, veh_stats, current_time)` | 추적 차량을 선택하거나 유지하고 SUMO-GUI 카메라를 갱신합니다. |
| `current_protagonist` | 현재 추적 중인 차량 ID를 반환합니다. |
| `on_vehicle_parked(vid)` | 추적 차량이 주차하면 추적 대상을 해제합니다. |

### 7.5 `scripts/core/monitor.py`

| 클래스 / 함수 | 기능 |
| --- | --- |
| `MultiprocessingPlotter` | 별도 프로세스에서 실시간 matplotlib 차트를 그립니다. |
| `send_data(step, veh_stats)` | 차량 상태에서 주차 수, 평균 시간, 연료, 속도 등의 지표를 추출합니다. |
| `close()` | 플로팅 프로세스에 중지 신호를 보내고 종료를 기다립니다. |
| `_render_full()` | 시나리오 A용 6개 패널 모니터입니다. |
| `_render_compact()` | 시나리오 B용 4개 패널 모니터입니다. |

### 7.6 `scripts/core/recording.py`

| 클래스 / 함수 | 기능 |
| --- | --- |
| `place_sumo_left_half()` | Windows에서 SUMO-GUI를 화면 왼쪽 절반으로 이동합니다. |
| `ScreenRecorder.start()` | ffmpeg `gdigrab`로 데스크톱 녹화를 시작합니다. |
| `ScreenRecorder.stop()` | ffmpeg를 정상 종료해 중단된 실행에서도 영상 생성을 최대한 보장합니다. |
| `prepare_visual_session()` | 창 배치, 녹화 시작, 프리롤 대기를 수행합니다. |

### 7.7 `scripts/core/reset_db.py`

| 함수 | 기능 |
| --- | --- |
| `reset_database(clear_logs=False, scenario_to_clear=None)` | 주차 점유와 가격을 초기화하고 전체 또는 특정 시나리오 로그를 선택적으로 삭제합니다. |

### 7.8 `scripts/run_scenario_A_baseline.py`

| 함수 | 기능 |
| --- | --- |
| `_load_spots()` | 데이터베이스와 `parking.add.xml`에서 용량, edge, 시작 위치를 로드합니다. |
| `_load_edges()` | `demo.net.xml`에서 edge 끝점, 노드, 길이를 추출합니다. |
| `_build_opposite_map()` | 반대 edge 조회 테이블을 생성합니다. |
| `_build_outgoing_map()` | 하류 edge 조회 테이블을 생성합니다. |
| `_spots_by_edge()` | 빠른 도로 탐색을 위해 주차 공간을 edge별로 그룹화합니다. |
| `_init_stats()` | 차량별 상태를 초기화합니다. |
| `_settle()` | 성공 주차 결과를 기록합니다. |
| `_settle_lost()` | 실패 또는 소실 차량을 기록합니다. |
| `_process_vehicle()` | 시나리오 A 단일 차량의 지표, 탐색, 주차, 타임아웃, 재라우팅을 처리합니다. |
| `run_baseline()` | 시나리오 A 메인 진입점입니다. |

### 7.9 `scripts/run_scenario_B_smart.py`

| 함수 | 기능 |
| --- | --- |
| `_load_spots()` | 데이터베이스에서 주차 용량, 가격, edge 정보를 읽습니다. |
| `_compute_positions()` | TraCI 시작 후 주차 공간의 edge 좌표를 계산합니다. |
| `_build_pricing_index()` | 반복 집계를 줄이기 위해 도로변 주차 그룹과 노외 주차장 인덱스를 미리 계산합니다. |
| `_price_from_rate()` | 점유율에 따라 기본가, 1.5배, 2배 가격을 반환합니다. |
| `_compute_pricing()` | 점유율 70% 초과 시 1.5배, 90% 초과 시 2배로 가격을 갱신합니다. |
| `_find_best_spot()` | 거리와 가격을 이용해 최소 비용 주차 공간을 선택합니다. |
| `_assign_vehicle()` | 목표 edge, 주차 정지 명령, 초기 차량 상태를 설정합니다. |
| `_settle()` | 차량 결과를 `Cruising_Logs`에 기록합니다. |
| `_handle_departed()` | 새로 출발한 차량에 주차 공간을 배정합니다. |
| `_process_driving()` | 주행 차량을 갱신하고 주차 성공 또는 차량 소실을 감지합니다. |
| `run_smart_booking_with_pricing()` | 시나리오 B 메인 진입점입니다. |

### 7.10 기타 스크립트

| 스크립트 / 함수 | 기능 |
| --- | --- |
| `scripts/init_db.py::init_database()` | `configs/schema.sql`을 읽고 실행합니다. |
| `scripts/prepare_simulation.py::run_step()` | 단일 준비 단계를 실행하고 종료 코드를 확인합니다. |
| `scripts/prepare_simulation.py::main()` | 도로망, 주차, 교통, 데이터베이스 준비를 순서대로 실행합니다. |
| `scripts/run_dashboard.py::fetch_data()` | Streamlit 대시보드용 시나리오 지표를 `Cruising_Logs`와 `Simulation_Runs`에서 집계합니다. |

---

## 8. 지표 기준

프로젝트는 데이터베이스에 실제로 기록된 지표만 보고해야 합니다.

- 성공 주차 수: `final_spot_id IS NOT NULL`
- 실패 또는 소실 수: `final_spot_id IS NULL`
- 평균 탐색 시간: `AVG(search_time_sec)`
- 전체 주차 완료 시간: `Simulation_Runs.completion_time_sec`
- 주차율: `Simulation_Runs.parking_rate`
- 총 연료 소비: `SUM(total_fuel_mg)`
- 시나리오 A 순항 거리: `SUM(cruising_distance_m)`

현재 두 시나리오 모두 100% 주차율에 도달하므로 보고서와 대시보드는 성공률을 주요 비교 지표로 사용하지 않아야 합니다. 핵심 비교 대상은 모든 차량의 주차 완료에 필요한 전역 시뮬레이션 시간입니다.

수집되거나 데이터베이스에 기록되지 않은 지표는 보고서, 논문, 대시보드에서 실측 결과로 다루면 안 됩니다.
