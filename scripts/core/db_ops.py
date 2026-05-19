"""数据库操作：日志记录、运行摘要与车位状态同步。"""


def ensure_simulation_runs_table(cursor):
    """确保场景级运行摘要表存在。"""
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS Simulation_Runs (
           run_id SERIAL PRIMARY KEY,
           scenario VARCHAR(20) NOT NULL,
           completion_time_sec FLOAT NOT NULL,
           total_vehicles INT NOT NULL,
           parked_vehicles INT NOT NULL,
           failed_vehicles INT NOT NULL,
           parking_rate FLOAT NOT NULL,
           created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )


def ensure_cruising_logs_environment_columns(cursor):
    """为单车日志表补齐环境排放字段，兼容旧数据库结构。"""
    cursor.execute(
        """ALTER TABLE Cruising_Logs
           ADD COLUMN IF NOT EXISTS total_co2_mg FLOAT NOT NULL DEFAULT 0,
           ADD COLUMN IF NOT EXISTS total_nox_mg FLOAT NOT NULL DEFAULT 0,
           ADD COLUMN IF NOT EXISTS total_pmx_mg FLOAT NOT NULL DEFAULT 0"""
    )


def log_cruise(
    cursor,
    vid,
    scenario,
    search_time,
    cruise_dist,
    total_fuel,
    spot_id,
    total_co2=0.0,
    total_nox=0.0,
    total_pmx=0.0,
):
    """写入一辆车的寻位结果、行驶距离和累计排放。"""
    cursor.execute(
        """INSERT INTO Cruising_Logs
           (vehicle_id, scenario, search_time_sec, cruising_distance_m,
            total_fuel_mg, total_co2_mg, total_nox_mg, total_pmx_mg,
            final_spot_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            vid,
            scenario,
            search_time,
            cruise_dist,
            total_fuel,
            total_co2,
            total_nox,
            total_pmx,
            spot_id,
        ),
    )


def log_run_summary(
    cursor,
    conn,
    scenario,
    completion_time_sec,
    total_vehicles,
    parked_vehicles,
    failed_vehicles,
):
    """写入一个场景的完成时间、停车成功数和失败数摘要。"""
    ensure_simulation_runs_table(cursor)
    parking_rate = parked_vehicles / total_vehicles if total_vehicles else 0.0
    cursor.execute(
        """INSERT INTO Simulation_Runs
           (scenario, completion_time_sec, total_vehicles, parked_vehicles,
            failed_vehicles, parking_rate)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (
            scenario,
            completion_time_sec,
            total_vehicles,
            parked_vehicles,
            failed_vehicles,
            parking_rate,
        ),
    )
    conn.commit()


def sync_spots(cursor, conn, spots_data):
    """同步场景 A 的车位占用状态。"""
    sync = [(d["occupied"], sid) for sid, d in spots_data.items()]
    cursor.executemany(
        "UPDATE Parking_Spots SET occupied = %s WHERE spot_id = %s", sync
    )
    conn.commit()


def sync_spots_priced(cursor, conn, spots_data):
    """同步场景 B 的预订占用状态和动态价格。"""
    sync = [(d["booked"], d["current_price"], sid) for sid, d in spots_data.items()]
    cursor.executemany(
        "UPDATE Parking_Spots SET occupied = %s, current_price = %s WHERE spot_id = %s",
        sync,
    )
    conn.commit()
