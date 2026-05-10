"""
app/db_conn.py
==============
[V59.6] ClickHouse 连接管理：懒加载 + 阻塞优化
"""
import os
import clickhouse_connect
from loguru import logger

_CK_GLOBAL_CLIENT = None

# [V68.1] 代理穿透：强制禁用针对 localhost 的代理拦截，防止 VPN/Clash 导致 10061 错误
import os as _os
_os.environ['NO_PROXY'] = 'localhost,127.0.0.1,::1'
_os.environ['no_proxy'] = 'localhost,127.0.0.1,::1'

def get_clickhouse_client():
    global _CK_GLOBAL_CLIENT
    
    if _CK_GLOBAL_CLIENT:
        try:
            _CK_GLOBAL_CLIENT.query("SELECT 1")
            return _CK_GLOBAL_CLIENT
        except:
            _CK_GLOBAL_CLIENT = None

    host = _os.getenv("CLICKHOUSE_HOST", "localhost")
    port = int(_os.getenv("CLICKHOUSE_PORT", "8123"))
    user = _os.getenv("CLICKHOUSE_USER", "default")
    password = _os.getenv("CLICKHOUSE_PASSWORD", "")

    # ── [V68.5] 物理自愈：尝试多种路径穿透网络阻断 ─────────────────────────
    # 路径 1: 标准 localhost (已通过 NO_PROXY 保护)
    try:
        logger.info(f"🔌 [DB_CONN] 尝试路径 1: {host}:{port} (HTTP)...")
        _CK_GLOBAL_CLIENT = clickhouse_connect.get_client(
            host=host, port=port, username=user, password=password,
            connect_timeout=5, send_receive_timeout=10
        )
        logger.success("✅ [DB_CONN] 路径 1 连接成功！")
        return _CK_GLOBAL_CLIENT
    except Exception as e1:
        logger.warning(f"⚠️ [DB_CONN] 路径 1 失败: {e1}")

    # 路径 2: 探测 WSL2 虚拟 IP (针对 localhost 转发失效场景)
    try:
        import subprocess
        logger.info("🔌 [DB_CONN] 尝试路径 2: 探测 WSL IP 直连...")
        res = subprocess.run(["wsl", "hostname", "-I"], capture_output=True, text=True, timeout=3)
        wsl_ip = res.stdout.split()[0] if res.stdout else None
        if wsl_ip:
            logger.info(f"🔗 [DB_CONN] 发现 WSL IP: {wsl_ip}, 尝试连接...")
            _CK_GLOBAL_CLIENT = clickhouse_connect.get_client(
                host=wsl_ip, port=8123, username=user, password=password,
                connect_timeout=5
            )
            logger.success(f"✅ [DB_CONN] 路径 2 ({wsl_ip}) 连接成功！")
            return _CK_GLOBAL_CLIENT
    except Exception as e2:
        logger.warning(f"⚠️ [DB_CONN] 路径 2 失败: {e2}")

    # 路径 3: Fallback 到 Native 协议 (针对 8123 端口被深度劫持场景)
    try:
        logger.info("🔌 [DB_CONN] 尝试路径 3: 切换 Native 协议 (Port 9000)...")
        import clickhouse_driver
        # 注意：Native 驱动返回的对象需要兼容包装，此处先尝试建立连接
        native_client = clickhouse_driver.Client(host=host, port=9000, user=user, password=password)
        native_client.execute("SELECT 1")
        
        # 封装一个兼容 clickhouse_connect 的 Proxy 对象
        class NativeProxy:
            def __init__(self, client): self.client = client
            def query(self, sql): 
                res = self.client.execute(sql, with_column_types=True)
                # 转换格式以兼容 clickhouse_connect 的结果对象
                class ResultProxy:
                    def __init__(self, r):
                        self.result_rows = r[0]
                        self.column_names = [col[0] for col in r[1]]
                return ResultProxy(res)
        
        _CK_GLOBAL_CLIENT = NativeProxy(native_client)
        logger.success("✅ [DB_CONN] 路径 3 (Native 9000) 连接成功！")
        return _CK_GLOBAL_CLIENT
    except Exception as e3:
        logger.error(f"❌ [DB_CONN] 所有路径均告失败。最后报错: {e3}")
        raise RuntimeError(f"无法建立 ClickHouse 连接。请检查服务是否开启或网络是否存在物理干扰。")
