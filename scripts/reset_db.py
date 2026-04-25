import sys

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.dbspre.database import get_db_connection


def reset_database(clear_logs=False):
    """
    数据库状态重置工具。
    在仿真开始前还原停车位的初始状态，并根据参数决定是否清空历史仿真日志数据。

    Args:
        clear_logs (bool): 若为 True，则彻底清空 cruising_Logs 日志表并重置其主键序列；
                           若为 False，则仅将 Parking_Spots 表的状态和价格恢复为基础设置。
    """
    print("🔌 正在连接数据库...")
    try:
        conn = get_db_connection()  # type: ignore
        cursor = conn.cursor()

        # 根据配置决定是否清理并重置仿真记录表
        if clear_logs:
            print("🧹 正在彻底清空 cruising_Logs 仿真日志表...")
            cursor.execute("TRUNCATE TABLE cruising_Logs RESTART IDENTITY;")
        else:
            print("⏭️ 跳过清空日志，仅重置停车场表。")

        # 统一将车位状态恢复为未占用，且将当前定价回退为基础价格
        cursor.execute(
            "UPDATE Parking_Spots SET occupied = 0, current_price = base_price;"
        )

        conn.commit()
        print("✅ 数据库重置成功！系统已准备好进行下一次干净的仿真实验。")

    except Exception as e:
        print(f"❌ 重置失败: {e}")
    finally:
        # 确保数据库连接资源被正确释放
        if "cursor" in locals():
            cursor.close()
        if "conn" in locals():
            conn.close()


if __name__ == "__main__":
    # 解析命令行参数：若包含 '--all' 则完全清空日志表
    should_clear_logs = "--all" in sys.argv
    reset_database(clear_logs=should_clear_logs)
