# ITS 스마트 주차 할당 및 순항 감소 시뮬레이션 시스템

<p align="center">
  <em>지능형 주차 예약 및 동적 가격 책정 시뮬레이션 시스템</em>
</p>

<p align="center">
    <img src="https://img.shields.io/badge/Python-3.10-blue.svg" alt="Python Version">
    <img src="https://img.shields.io/badge/SUMO-Simulation-orange.svg" alt="SUMO">
    <img src="https://img.shields.io/badge/Database-PostgreSQL-blue.svg" alt="PostgreSQL">
</p>

> **다국어 문서 | Multilingual Documentation:** [English](README.en.md) | [中文](README.md) | 한국어 | [日本語](README.ja.md)

---

## 목차

- [프로젝트 개요](#프로젝트-개요)
- [데이터베이스 설계](#데이터베이스-설계)
- [프로젝트 구조](#프로젝트-구조)
- [빠른 시작](#빠른-시작)
- [소프트웨어 운영 방법](#소프트웨어-운영-방법)
- [모듈 참조](#모듈-참조)

---

## 프로젝트 개요

본 프로젝트는 **SUMO**(Simulation of Urban MObility) 미시 교통 시뮬레이션과 **PostgreSQL** 실시간 예약 데이터베이스를 결합하여 도심 업무 지구(CBD)의 **주차 순항 문제**(cruising-for-parking)를 해결합니다.

**두 가지 시나리오 비교:**

| 시나리오 | 설명 |
|----------|-------------|
| **A — 베이스라인** | 차량이 예약 시스템 없이 도로 네트워크 전체를 맹목적으로 순항하며 빈 주차 공간을 탐색합니다. |
| **B — 스마트 예약 및 가격 책정** | 차량 생성 시 거리와 동적 급증 가격을 결합한 비용 함수를 통해 최적의 주차 공간이 할당됩니다. |

**핵심 기능:**

- **주차 스키마** — SUMO 주차 구역을 관계형 데이터베이스에 매핑하여 실시간 상태 추적.
- **순항 감지** — TraCI를 통해 각 차량을 모니터링하여 탐색 시간, 주행 거리, 연료 소비량 기록.
- **예약 엔진** — SQL 상태 쿼리를 기반으로 진입 차량에 가용 주차 공간 할당 및 예약.
- **동적 가격 책정** — 급증 가격제 구현: 점유율 70% 초과 시 기본 요금의 1.5배, 90% 초과 시 2배.
- **성능 대시보드** — Streamlit 기반 웹 대시보드에서 두 시나리오의 주요 지표 비교.

---

## 데이터베이스 설계

시스템은 실시간 상태 동기화를 위해 **PostgreSQL**을 사용합니다. 연결 매개변수는 프로젝트 루트의 `.env` 파일에 구성됩니다. 스키마는 `scripts/generate_parking.py`에 의해 자동 생성되어 `configs/schema.sql`에 기록됩니다.

### 테이블: `Parking_Spots` (주차 공간 상태)

모든 오프스트리트 및 온스트리트 주차 공간의 실시간 상태를 기록합니다.

| 열 | 유형 | 설명 |
|--------|------|-------------|
| `spot_id` | `VARCHAR(50)` | 기본 키; 고유 주차 공간 식별자 (예: `off_street_0`, `on_street_42`) |
| `edge_id` | `VARCHAR(50)` | 주차 공간이 속한 도로 세그먼트(edge) |
| `spot_type` | `ENUM('on-street', 'off-street')` | 유형: 노상 주차 또는 주차장 |
| `capacity` | `INT` | 수용 가능한 최대 차량 수 |
| `occupied` | `INT` | 현재 점유/예약된 수 (기본값 0) |
| `base_price` | `DECIMAL(5,2)` | 기본 주차 요금 |
| `current_price` | `DECIMAL(5,2)` | 급증 조정 주차 요금 (시나리오 B에서 실시간 업데이트) |

### 테이블: `Cruising_Logs` (순항 로그)

각 차량의 주차 탐색 생애 주기와 환경 비용을 기록합니다.

| 열 | 유형 | 설명 |
|--------|------|-------------|
| `log_id` | `SERIAL` | 기본 키; 자동 증가 |
| `vehicle_id` | `VARCHAR(50)` | 차량 식별자 |
| `scenario` | `VARCHAR(20)` | 시나리오 이름 (`Baseline` 또는 `Smart_Booking_Priced`) |
| `search_time_sec` | `FLOAT` | 주차 탐색 소요 시간(초) |
| `cruising_distance_m` | `FLOAT` | 탐색 중 총 주행 거리(미터) |
| `final_spot_id` | `VARCHAR(50)` | 최종 주차 공간 (실패 시 NULL) |
| `total_fuel_mg` | `FLOAT` | 탐색 중 소비된 총 연료(밀리그램) |
| `created_at` | `TIMESTAMP` | 자동 생성된 로그 타임스탬프 |

---

## 프로젝트 구조

```text
dbspre/
├── configs/                          # SUMO 설정 파일 및 SQL 스키마
│   ├── demo.net.xml                  # 15×15 격자 도로 네트워크
│   ├── demo.rou.xml                  # 차량 경로 설정
│   ├── demo.sumocfg                  # SUMO 통합 실행 설정
│   ├── demo.trips.xml                # 차량 통행 출발지 및 목적지
│   ├── gui-settings.xml              # SUMO GUI 시각 설정
│   ├── parking.add.xml               # 주차장 형상 및 공간 배치
│   └── schema.sql                    # 데이터베이스 DDL 및 초기 데이터
├── scripts/                          # Python 스크립트
│   ├── core/                         # 공유 핵심 모듈
│   │   ├── __init__.py               # 패키지 마커
│   │   ├── config.py                 # 시뮬레이션 상수 및 경로
│   │   ├── connection.py             # PostgreSQL 연결 팩토리
│   │   ├── db_ops.py                 # 데이터베이스 CRUD 작업
│   │   ├── gui_tracker.py            # SUMO-GUI 카메라 추적 로직
│   │   ├── monitor.py                # 실시간 matplotlib 플로팅 에이전트
│   │   ├── parking_logic.py          # 도로 수준 주차 탐색 로직 (시나리오 A)
│   │   └── reset_db.py               # 데이터베이스 상태 초기화 유틸리티
│   ├── generate_network.ps1          # PowerShell: netgenerate로 격자 네트워크 생성
│   ├── generate_parking.py           # 주차장 및 노상 주차 공간 생성 (XML + SQL)
│   ├── generate_traffic.py           # 2,500대의 CBD 방향 통근 통행 생성
│   ├── init_db.py                    # schema.sql 실행으로 데이터베이스 초기화
│   ├── prepare_simulation.py         # 원클릭 준비: 네트워크 → 주차 → 통행 → DB 초기화
│   ├── run_dashboard.py              # Streamlit 성능 비교 대시보드
│   ├── run_scenario_A_baseline.py    # 시나리오 A: 맹목적 순항 (예약 없음)
│   └── run_scenario_B_smart.py       # 시나리오 B: 동적 가격 책정 스마트 예약
├── .env.example                      # 데이터베이스 연결 템플릿
├── requirements.txt                  # Python 의존성 목록
└── README.md                         # 이 문서
```

---

## 빠른 시작

### 사전 요구사항

- **Python 3.10** (가상 환경 관리에 `uv` 사용 권장)
- **PostgreSQL** 로컬 또는 원격 실행
- **SUMO**(Simulation of Urban MObility) 설치 및 시스템 `PATH`에 추가, `SUMO_HOME` 환경 변수 설정
- **VS Code** (권장). Pylance 지원을 위해 `.vscode/settings.json`에 다음을 추가하세요:

```json
{
    "python.analysis.extraPaths": ["${workspaceFolder}/scripts"]
}
```

### 1. 클론 및 의존성 설치

```bash
git clone https://github.com/bulong0211/dbspre.git
cd dbspre

# uv 사용 (권장)
uv sync

# 또는 pip 사용
pip install -r requirements.txt
```

### 2. 데이터베이스 설정

환경 템플릿을 복사하고 PostgreSQL 자격 증명을 입력하세요:

```bash
cp .env.example .env
```

`.env` 편집:

```env
DB_NAME=smart_parking
DB_USER=postgres
DB_PASSWORD=your_password_here
DB_HOST=localhost
DB_PORT=5432
```

> **참고:** PostgreSQL에 먼저 데이터베이스를 생성하세요 (예: `CREATE DATABASE smart_parking;`).

### 3. 시뮬레이션 환경 준비

`configs/`에 네트워크 및 주차 파일이 이미 있으면 이 단계를 건너뛰세요. 그렇지 않으면 원클릭 준비 스크립트를 실행하세요:

```bash
uv run scripts/prepare_simulation.py
```

네트워크 생성 → 주차 생성 → 통행 생성 → 데이터베이스 초기화를 순차적으로 실행합니다.

### 4. 시뮬레이션 실행

```bash
# 시나리오 A — 베이스라인 (맹목적 순항, 시작 시 모든 과거 로그 삭제)
uv run scripts/run_scenario_A_baseline.py

# 시나리오 B — 스마트 예약 및 동적 가격 책정
uv run scripts/run_scenario_B_smart.py
```

각 시뮬레이션은 최대 7,200초(2시간) 또는 2,500대의 차량이 모두 처리될 때까지 실행됩니다. 실시간 지표가 matplotlib 창에 표시되며 결과는 PostgreSQL에 기록됩니다.

### 5. 대시보드 보기

Streamlit 성능 비교 대시보드를 실행하세요:

```bash
uv run streamlit run scripts/run_dashboard.py
```

브라우저에서 `http://localhost:8501`을 열어 두 시나리오 간의 성공률, 탐색 시간, 연료 소비량, 순항 거리를 비교하세요.

---

## 소프트웨어 운영 방법

### 시뮬레이션 흐름

두 시나리오 모두 TraCI를 통해 SUMO와 통합된 동일한 상위 수준 루프를 따릅니다:

```
1. 데이터베이스 상태 초기화
2. PostgreSQL에 연결
3. 주차 공간 데이터 로드
4. 데모 설정으로 SUMO 시작
5. 시뮬레이션에 활성 차량이 있고 시간이 7200초 미만인 동안:
   a. 시뮬레이션 한 단계 진행
   b. GUI 카메라 추적 업데이트
   c. 새로 출발한 차량 처리 (주차 공간 할당 / 경로 설정)
   d. 주행 중인 활성 차량 처리 (지표 업데이트, 주차 감지, 타임아웃 처리)
   e. 실시간 플로터 새로고침
   f. 조기 완료 확인 (2500대 모두 처리)
   g. 60초마다 주차 공간 점유율 및 가격을 데이터베이스에 동기화
6. 최종 데이터베이스 동기화
7. SUMO, 플로터, 데이터베이스 연결 종료
```

### 시나리오별 주요 차이점

| 측면 | 시나리오 A | 시나리오 B |
|--------|-----------|-----------|
| 주차 공간 할당 | 없음 (차량이 도로 스캔으로 공간 탐색) | 생성 시 비용 함수를 통해 최적 공간 할당 |
| 내비게이션 | 무작위 edge 재라우팅 | 할당된 공간으로 직접 경로 |
| 동적 가격 책정 | 사용 안 함 | 매 단계마다 급증 가격 업데이트 |
| 주행 행동 | `setSpeedFactor(0.4)`, `setImperfection(0.9)` | 동일 매개변수 |
| 타임아웃 | 120초 타겟 타임아웃 후 재라우팅 | 120초 타겟 타임아웃 후 텔레포트 |
| 주차 로직 | `parking_logic.py` (스캔, try_park, 재라우팅) | `changeTarget` + `setParkingAreaStop` |

---

## 모듈 참조

### `core/config.py` — 설정 상수 및 경로

조정 가능한 모든 시뮬레이션 매개변수를 정의합니다.

| 상수 | 값 | 설명 |
|----------|-------|-------------|
| `CONFIG_DIR` | `Path(...)/configs` | SUMO 설정 파일 경로 |
| `SIMULATION_DURATION_LIMIT` | `7200` | 최대 시뮬레이션 시간(초) |
| `TOTAL_VEHICLES_TARGET` | `2500` | 처리할 총 차량 수 |
| `SIGHT_DISTANCE` | `80.0` | 도로 스캔을 위한 전방 가시 거리(미터) |
| `TARGET_TIMEOUT` | `120` | 포기 전 주차 공간에 고정된 최대 시간(초) |
| `DB_SYNC_INTERVAL` | `60` | 데이터베이스 동기화 간격(초) |
| `SCENARIO_A_NAME` | `"Baseline"` | 데이터베이스에서의 시나리오 A 식별자 |
| `SCENARIO_B_NAME` | `"Smart_Booking_Priced"` | 데이터베이스에서의 시나리오 B 식별자 |
| `WEIGHT_DISTANCE` | `1.0` | 비용 함수에서의 거리 가중치 (시나리오 B) |
| `WEIGHT_PRICE` | `100.0` | 비용 함수에서의 가격 가중치 (시나리오 B) |

---

### `core/connection.py` — 데이터베이스 연결 팩토리

| 함수 | 설명 |
|----------|-------------|
| `get_db_config()` | 환경 변수(`.env`)에서 데이터베이스 연결 매개변수를 읽습니다. `dbname`, `user`, `password`, `host`, `port` 키가 있는 사전을 반환합니다. |
| `get_db_connection()` | `get_db_config()`를 사용하여 `psycopg2` 연결 객체를 생성하고 반환합니다. |

---

### `core/db_ops.py` — 데이터베이스 작업

| 함수 | 서명 | 설명 |
|----------|-----------|-------------|
| `log_cruise()` | `(cursor, vid, scenario, search_time, cruise_dist, total_fuel, spot_id)` | 차량의 탐색 결과를 기록하는 행을 `Cruising_Logs`에 삽입합니다. |
| `sync_spots()` | `(cursor, conn, spots_data)` | 모든 주차 공간의 `Parking_Spots.occupied`를 일괄 업데이트합니다. 시나리오 A에서 사용됩니다. |
| `sync_spots_priced()` | `(cursor, conn, spots_data)` | 모든 주차 공간의 `occupied` 및 `current_price`를 모두 일괄 업데이트합니다. 시나리오 B에서 사용됩니다. |

---

### `core/gui_tracker.py` — SUMO-GUI 카메라 추적

무작위로 선택된 "주인공" 차량을 따라가는 SUMO-GUI 카메라를 관리하여 주차 탐색의 1인칭 시점을 제공합니다.

| 클래스 | 설명 |
|-------|-------------|
| `GUITracker` | 현재 주인공 차량을 추적하고 설정 가능한 쿨다운으로 카메라 전환을 관리합니다. |

| 메서드 | 설명 |
|--------|-------------|
| `__init__()` | 추적기 상태 초기화: `protagonist=None`, `total_tracked=0`, `last_track_time=0.0`. |
| `update(active_vehicles, veh_stats, current_time)` | 매 단계마다 호출됩니다. 현재 주인공을 잃으면 새 주인공을 선택합니다. SUMO가 내부 상태를 잃으면 추적을 다시 적용합니다. `GUI_REFRESH_INTERVAL`로 조절됩니다. |
| `on_vehicle_parked(vid)` | 주인공이 성공적으로 주차하면 주인공을 해제합니다. |

| 속성 | 설명 |
|----------|-------------|
| `current_protagonist` | 현재 추적 중인 차량 ID(또는 `None`)를 반환합니다. |

---

### `core/monitor.py` — 실시간 플로팅 에이전트

별도 프로세스에서 matplotlib을 사용하여 시뮬레이션 지표의 실시간 시각화를 제공합니다.

| 클래스 | 설명 |
|-------|-------------|
| `MultiprocessingPlotter` | 차량 통계에서 지표를 추출하여 `multiprocessing.Queue`를 통해 백그라운드 렌더링 프로세스로 전송하는 메인 프로세스 프록시입니다. |

| 메서드 | 설명 |
|--------|-------------|
| `__init__(window_title, layout="A")` | 렌더러 하위 프로세스를 시작합니다. `layout="A"`는 6개 차트(순항 지표 포함), `layout="B"`는 4개 차트(주차, 탐색 시간, 연료, 속도)를 표시합니다. |
| `send_data(step, veh_stats)` | 현재 지표(활성 수, 주차 수, 평균 탐색 시간, 총 연료, 평균 속도)를 계산하여 렌더링 큐에 푸시합니다. |
| `close()` | `STOP` 신호를 보내고 렌더러 프로세스를 종료합니다. |

---

### `core/parking_logic.py` — 도로 수준 주차 탐색 (시나리오 A)

실제 운전자가 도로와 교차로를 스캔하여 빈 주차 공간을 찾는 것을 시뮬레이션합니다. 핵심 원칙: SUMO의 `setParkingAreaStop`이 주차 가능 여부의 유일한 판단자입니다.

| 함수 | 서명 | 설명 |
|----------|-----------|-------------|
| `reroute_random()` | `(vid, all_edges, opposite_map, outgoing_map)` | 현재 edge, 반대편 edge, 인접 edge를 제외한 무작위 edge를 새 목적지로 할당합니다. 실패 시 `False` 반환. |
| `scan_street()` | `(vid, current_edge, current_lanepos, spots_by_edge, all_spots, opposite_map, outgoing_map, edge_lengths, full_scan)` | 현재 도로(및 선택적으로 교차 방향과 다음 경로 edge)에서 시야 거리 내 빈 공간을 스캔합니다. `(spot_id, spot_edge)` 또는 `(None, None)` 반환. |
| `try_park()` | `(vid, spot_id, spot_edge, stats, current_edge, all_spots)` | 발견된 공간에 주차를 시도합니다. 같은 edge: `setParkingAreaStop` 호출. 다른 edge: `changeTarget` 호출 및 보류 중인 예약 기록. 이미 확정된 경우 새 공간 거부. 성공 시 `True` 반환. |
| `check_pending()` | `(vid, stats, current_edge, all_spots, all_edges, opposite_map, outgoing_map)` | 보류 중인 공간이 있는 edge에 차량이 도착하면 주차를 완료하려고 시도합니다. 공간이 점유되었으면 정리합니다. |
| `handle_occupied()` | `(vid, stats, current_edge, all_spots, all_edges, opposite_map, outgoing_map)` | 목표 공간이 점유되거나 차량이 목표 도로를 벗어났을 때 감지합니다. 공간을 해제하고 재라우팅을 트리거합니다. |

---

### `core/reset_db.py` — 데이터베이스 상태 초기화

| 함수 | 서명 | 설명 |
|----------|-----------|-------------|
| `reset_database()` | `(clear_logs=False, scenario_to_clear=None)` | `Parking_Spots.occupied`를 0으로, `current_price`를 `base_price`로 재설정합니다. `clear_logs=True`이면 `Cruising_Logs`를 비웁니다. `scenario_to_clear`가 제공되면 해당 시나리오의 로그만 삭제합니다. |

---

### `run_scenario_A_baseline.py` — 시나리오 A: 맹목적 순항

차량이 예약 시스템 없이 무작위 목적지를 할당받고 도로를 스캔하여 빈 주차 공간을 찾아야 하는 기준 시나리오를 구현합니다.

**내부 함수:**

| 함수 | 설명 |
|----------|-------------|
| `_load_spots(cursor)` | 데이터베이스에서 주차 공간 메타데이터를 로드하고 `parking.add.xml`을 파싱하여 기하 데이터(`startPos`, `lane`)를 얻습니다. |
| `_load_edges()` | `demo.net.xml`을 파싱하여 from/to 노드 좌표와 계산된 길이가 있는 도로 edge 사전을 구축합니다. |
| `_init_stats(current_time)` | 새로 생성된 차량을 위한 초기 통계 사전을 생성합니다. |
| `_settle(vid, stats, current_time, current_dist, spot_id, cursor, conn)` | 성공적으로 주차한 차량의 결과를 데이터베이스에 기록합니다. |
| `_settle_lost(vid, stats, current_time, cursor, conn)` | 텔레포트/손실된 차량의 결과를 `final_spot_id = NULL`로 기록합니다. |
| `_process_vehicle(...)` | 단일 순항 차량을 위한 단계별 상태 머신: 주차 상태 확인, 보류 중인 공간 처리, 도로 스캔, 주차 시도, 필요 시 재라우팅. |
| `run_baseline()` | 메인 진입점. 전체 시뮬레이션 수명 주기를 조율합니다. |

---

### `run_scenario_B_smart.py` — 시나리오 B: 스마트 예약 및 동적 가격 책정

차량이 생성 시 비용 함수를 통해 최적의 주차 공간을 할당받고, 가격이 실시간 점유율에 따라 동적으로 조정되는 지능형 시나리오를 구현합니다.

**내부 함수:**

| 함수 | 설명 |
|----------|-------------|
| `_load_spots(cursor)` | 데이터베이스에서 가격 정보가 포함된 주차 공간 데이터를 로드합니다. |
| `_compute_positions(all_spots)` | 각 주차 공간 lane의 물리적 좌표를 가져옵니다 (TraCI 실행 필요). |
| `_compute_pricing(all_spots)` | 매 시뮬레이션 단계마다 급증 가격을 계산합니다. 소규모 노상 공간(용량 ≤ 3)은 점유율 계산을 위해 도로별로 집계됩니다. 가격 단계: >90% → 2배, >70% → 1.5배, 그 외 기본. |
| `_find_best_spot(vehicle_pos, all_spots)` | `cost = 거리 × WEIGHT_DISTANCE + 현재 가격 × WEIGHT_PRICE`를 최소화하여 최적의 주차 공간을 선택합니다. 가용 용량이 있는 공간만 고려합니다. |
| `_assign_vehicle(vid, spot_id, all_spots, veh_stats, current_time)` | `changeTarget` 및 `setParkingAreaStop`을 통해 차량을 할당된 공간으로 라우팅합니다. 모든 TraCI 호출이 성공한 후에만 예약 카운터를 증가시킵니다(원자성). |
| `_settle(vid, stats, current_time, spot_id, cursor, conn)` | 차량 결과를 `Cruising_Logs` 테이블에 기록합니다. |
| `_handle_departed(departed, all_spots, veh_stats, current_time)` | 새로 생성된 차량 처리: 주행 매개변수 구성, 최적의 공간 찾기 및 할당. 할당 실패 시 경고 기록. |
| `_process_driving(veh_stats, sub_results, current_time, all_spots, cursor, conn, gui)` | 모든 주행 중인 차량의 단계별 처리: 속도/거리/연료 지표 업데이트, 텔레포트 감지, 목표 타임아웃 적용(정체 차량 해제), 성공적 주차 감지. |
| `run_smart_booking_with_pricing()` | 메인 진입점. 전체 시뮬레이션 수명 주기를 조율합니다. |

---

### 보조 스크립트

| 스크립트 | 설명 |
|--------|-------------|
| `generate_network.ps1` | SUMO의 `netgenerate`를 호출하여 15×15 CBD 격자 도로 네트워크를 생성합니다. |
| `generate_parking.py` | 도로 네트워크를 파싱하여 50개의 오프스트리트 주차장(각 38면)과 800개의 온스트리트 주차 공간(각 1면)을 생성하고 `parking.add.xml` 및 `schema.sql`을 출력합니다. |
| `generate_traffic.py` | 경계 진입 edge에서 CBD 핵심 지역 방향으로 2,500개의 통근 통행을 생성하고 출발 시간순으로 정렬하여 `demo.trips.xml`을 출력합니다. |
| `init_db.py` | PostgreSQL에 연결하고 `schema.sql`을 실행하여 테이블을 생성하고 초기 주차 공간 데이터를 삽입합니다. |
| `prepare_simulation.py` | 네트워크 생성 → 주차 생성 → 통행 생성 → 데이터베이스 초기화를 순차적으로 실행하는 원클릭 준비 오케스트레이터입니다. |
| `run_dashboard.py` | `Cruising_Logs`를 쿼리하고 시나리오 A 대 시나리오 B의 비교 KPI 카드와 차트(성공률, 탐색 시간, 연료 소비량, 순항 거리)를 렌더링하는 Streamlit 웹 대시보드입니다. |

| 함수 (대시보드) | 설명 |
|----------------------|-------------|
| `fetch_data()` | 시나리오별로 그룹화된 집계 시뮬레이션 지표를 PostgreSQL에서 쿼리합니다. 5초간 캐시됩니다. |
