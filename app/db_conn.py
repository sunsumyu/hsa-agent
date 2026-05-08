"""
app/db_conn.py
==============
[V59.6] ClickHouse 连接管理：懒加载 + 阻塞优化
"""
import os
import clickhouse_connect
from loguru import logger

_CK_GLOBAL_CLIENT = None

def get_clickhouse_client():
    global _CK_GLOBAL_CLIENT
    
    if _CK_GLOBAL_CLIENT:
        try:
            # 极速心跳
            _CK_GLOBAL_CLIENT.query("SELECT 1")
            return _CK_GLOBAL_CLIENT
        except:
            _CK_GLOBAL_CLIENT = None
            
    host = os.getenv("CLICKHOUSE_HOST", "127.0.0.1")
    try:
        # 将超时缩短为 3 秒，失败立刻报错不卡死
        client = clickhouse_connect.get_client(
            host=host,
            port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            username=os.getenv("CLICKHOUSE_USER", "default"),
            password=os.getenv("CLICKHOUSE_PASSWORD", ""),
            database=os.getenv("CLICKHOUSE_DB", "default"),
            connect_timeout=10,
            send_receive_timeout=60
        )
        _CK_GLOBAL_CLIENT = client
        logger.info(f"✅ ClickHouse 物理连接成功: {host}")
        return _CK_GLOBAL_CLIENT
    except Exception as e:
        error_msg = f"❌ [CLICKHOUSE FATAL] 物理连接失败: {e}"
        logger.critical(error_msg)
        raise RuntimeError(error_msg) from e
