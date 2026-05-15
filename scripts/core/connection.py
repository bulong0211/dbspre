import os
import psycopg2
from typing import Dict, Any
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

def get_db_config() -> Dict[str, Any]:
    """获取数据库连接配置参数，支持通过环境变量进行覆盖。"""
    return {
        "dbname": os.environ.get("DB_NAME", "smart_parking"),
        "user": os.environ.get("DB_USER", "postgres"),
        "password": os.environ.get("DB_PASSWORD", "123456"),
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": os.environ.get("DB_PORT", "5432"),
    }

def get_db_connection():
    """建立并返回数据库连接对象。"""
    return psycopg2.connect(**get_db_config())
