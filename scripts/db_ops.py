"""数据库操作：日志记录与车位状态同步。"""


def log_cruise(cursor, vid, scenario, search_time, cruise_dist, total_fuel, spot_id):
    cursor.execute(
        """INSERT INTO Cruising_Logs
           (vehicle_id, scenario, search_time_sec, cruising_distance_m, total_fuel_mg, final_spot_id)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (vid, scenario, search_time, cruise_dist, total_fuel, spot_id),
    )


def sync_spots(cursor, conn, spots_data):
    sync = [(d["occupied"], sid) for sid, d in spots_data.items()]
    cursor.executemany(
        "UPDATE Parking_Spots SET occupied = %s WHERE spot_id = %s", sync
    )
    conn.commit()
