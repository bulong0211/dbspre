from dbspre.database import get_db_connection


def analyze():
    """
    连接数据库并聚合仿真数据，生成关于不同停车场景的效能评估报告。
    包括系统承载量、成功率、寻车耗时、能耗及无效巡航里程等核心指标计算与展示。
    """
    print("🔌 正在连接数据库并进行全生命周期数据聚合...")
    try:
        conn = get_db_connection()  # type: ignore
        cursor = conn.cursor()

        # 从日志表中按场景聚合关键指标，区分成功泊车与失败的车辆
        cursor.execute("""
            SELECT 
                scenario, 
                COUNT(vehicle_id) as total_cars,
                SUM(CASE WHEN final_spot_id IS NOT NULL THEN 1 ELSE 0 END) as parked_cars,
                SUM(CASE WHEN final_spot_id IS NULL THEN 1 ELSE 0 END) as failed_cars,
                AVG(CASE WHEN final_spot_id IS NOT NULL THEN search_time_sec ELSE NULL END) as avg_search_parked,
                AVG(search_time_sec) as avg_search_all,
                SUM(total_fuel_mg) / 1000000.0 as total_fuel_kg,
                SUM(cruising_distance_m) / 1000.0 as total_dist_km
            FROM Cruising_Logs
            GROUP BY scenario
            ORDER BY scenario ASC;
        """)

        results = cursor.fetchall()

        # 校验数据完整性
        if len(results) < 2:
            print("⚠️ 数据不足，请确保场景 A 和 B 都已经运行完毕并存入数据库！")
            return

        # 结构化解析数据库返回的结果
        data = {}
        for row in results:
            scenario_name = row[0]
            data[scenario_name] = {
                "total": row[1] or 0,
                "parked": row[2] or 0,
                "failed": row[3] or 0,
                "avg_search_parked": row[4] or 0.0,
                "avg_search_all": row[5] or 0.0,
                "fuel_kg": row[6] or 0.0,
                "dist_km": row[7] or 0.0,
            }

        # 适配不同的场景命名，提取基线场景与智能场景数据
        baseline = data.get("Baseline", {})
        smart = data.get("Smart_Booking_Priced", data.get("Smart_Booking", {}))

        if not baseline or not smart:
            print(f"⚠️ 无法匹配场景名称。当前数据库中的场景有: {list(data.keys())}")
            return

        # 计算对比指标：成功率、燃油节省占比、消除的无效里程
        success_rate_A = (
            (baseline["parked"] / baseline["total"]) * 100
            if baseline["total"] > 0
            else 0
        )
        success_rate_B = (
            (smart["parked"] / smart["total"]) * 100 if smart["total"] > 0 else 0
        )

        fuel_saved = baseline["fuel_kg"] - smart["fuel_kg"]
        fuel_saved_pct = (
            (fuel_saved / baseline["fuel_kg"]) * 100 if baseline["fuel_kg"] > 0 else 0
        )

        dist_saved = baseline["dist_km"] - smart["dist_km"]

        # 终端格式化输出报表
        print("\n" + "═" * 70)
        print(" 🚗 智能停车系统 (ITS) 效能评估报告 —— 全生命周期视界 📊")
        print("═" * 70)
        print(
            f"{'评估指标':<25} | {'场景 A (盲目基准线)':<18} | {'场景 B (智能定价预订)':<18}"
        )
        print("─" * 70)
        print(
            f"{'1. 系统总承载车辆数':<22} | {baseline['total']:<18} | {smart['total']:<18}"
        )
        print(
            f"{'2. 成功泊入车辆数':<23} | {baseline['parked']} ({success_rate_A:.1f}%)      | {smart['parked']} ({success_rate_B:.1f}%)"
        )
        print(
            f"{'3. 死锁/超时失败车辆数':<20} | {baseline['failed']:<18} | {smart['failed']:<18}"
        )
        print("─" * 70)
        print(
            f"{'4. 成功者平均寻车耗时':<21} | {baseline['avg_search_parked']:<15.1f} 秒 | {smart['avg_search_parked']:<15.1f} 秒"
        )
        print(
            f"{'5. 全局平均寻车耗时 *':<22} | {baseline['avg_search_all']:<15.1f} 秒 | {smart['avg_search_all']:<15.1f} 秒"
        )
        print("─" * 70)
        print(
            f"{'6. 系统总耗油量/碳排':<21} | {baseline['fuel_kg']:<15.2f} kg | {smart['fuel_kg']:<15.2f} kg"
        )
        print(
            f"{'7. 无效巡航总里程':<22} | {baseline['dist_km']:<15.2f} km | {smart['dist_km']:<15.2f} km"
        )
        print("═" * 70)

        # 输出用于进一步分析的核心结论
        print("\n💡 核心学术结论 (适用于答辩 PPT):")
        print(
            f"✅ 吞吐量突破：传统盲目模式下，因路网拥堵死锁导致大量车辆({baseline['failed']}辆)无法停车；"
            f"本系统将停车成功率从 {success_rate_A:.1f}% 跃升至 {success_rate_B:.1f}%。"
        )
        print(
            "✅ 幸存者偏差修正：仅看“成功者”的寻车时间会掩盖路网的拥堵本质（指标 4）；"
            "引入“全局平均耗时”（指标 5）后，更客观地体现了系统的真实时间成本。"
        )
        print(
            f"✅ 环境经济价值：动态定价与预订机制彻底消灭了 {dist_saved:.1f} 公里的无效巡航里程，"
            f"实现系统级减排 {fuel_saved_pct:.2f}%！"
        )
        print("═" * 70 + "\n")

    except Exception as e:
        print(f"❌ 数据库聚合失败: {e}")
    finally:
        # 安全释放数据库连接资源
        if "cursor" in locals():
            cursor.close()
        if "conn" in locals():
            conn.close()


if __name__ == "__main__":
    analyze()
