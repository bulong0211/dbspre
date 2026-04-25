import psycopg2
from pathlib import Path

from connection import get_db_connection

SQL_FILE = Path(__file__).resolve().parent.parent / "configs" / "schema.sql"


def init_database():
    print(f"正在读取 SQL 脚本: {SQL_FILE}")
    try:
        with open(SQL_FILE, "r", encoding="utf-8") as f:
            sql_script = f.read()
    except FileNotFoundError:
        print("❌ 错误: 找不到 SQL 文件，请先运行生成脚本。")
        return

    print("正在连接 PostgreSQL 数据库...")
    conn = None
    try:
        # 建立连接
        conn = get_db_connection()  # type: ignore
        cursor = conn.cursor()

        # 开启事务并执行脚本
        print("开始执行建表与数据插入事务...")
        cursor.execute(sql_script)

        # 提交事务
        conn.commit()
        print("✅ 成功！数据库结构已建立，所有停车位数据已成功灌入！")

        # 验证插入结果
        cursor.execute(
            "SELECT spot_type, COUNT(*) FROM Parking_Spots GROUP BY spot_type;"
        )
        results = cursor.fetchall()
        print("\n📊 数据库当前库存:")
        for row in results:
            print(f"  - {row[0]}: {row[1]} 个车位")

        cursor.close()

    except psycopg2.Error as e:
        print(f"❌ 数据库操作失败: {e}")
        if conn:
            conn.rollback()  # 发生错误时回滚事务，保证数据一致性
            print("🔄 事务已回滚。")
    finally:
        if conn:
            conn.close()
            print("🔒 数据库连接已关闭。")


if __name__ == "__main__":
    init_database()
