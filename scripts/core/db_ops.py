"""数据库操作：日志记录、运行摘要与车位状态同步。"""


def ensure_simulation_runs_table(cursor):
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


def log_cruise(cursor, vid, scenario, search_time, cruise_dist, total_fuel, spot_id):
    cursor.execute(
        """INSERT INTO Cruising_Logs
           (vehicle_id, scenario, search_time_sec, cruising_distance_m, total_fuel_mg, final_spot_id)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (vid, scenario, search_time, cruise_dist, total_fuel, spot_id),
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
    sync = [(d["occupied"], sid) for sid, d in spots_data.items()]
    cursor.executemany(
        "UPDATE Parking_Spots SET occupied = %s WHERE spot_id = %s", sync
    )
    conn.commit()


def sync_spots_priced(cursor, conn, spots_data):
    sync = [(d["booked"], d["current_price"], sid) for sid, d in spots_data.items()]
    cursor.executemany(
        "UPDATE Parking_Spots SET occupied = %s, current_price = %s WHERE spot_id = %s",
        sync,
    )
    conn.commit()
