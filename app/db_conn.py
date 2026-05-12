"""
app/db_conn.py
==============
[V59.6] ClickHouse 连接管理：懒加载 + 阻塞优化
"""
import os
import clickhouse_connect
import chardet
from loguru import logger

_CK_GLOBAL_CLIENT = None

# [V68.1] 代理穿透：强制禁用针对 localhost 的代理拦截，防止 VPN/Clash 导致 10061 错误
import os as _os
_os.environ['NO_PROXY'] = 'localhost,127.0.0.1,::1'
_os.environ['no_proxy'] = 'localhost,127.0.0.1,::1'

class CharsetProxy:
    """[V110.0] 统一编码网关：在驱动层强制拦截所有返回流，确保传输给 LLM 前统一转为 UTF-8"""
    def __init__(self, client):
        self.client = client
        # 兼容两种驱动
        self.is_native = hasattr(client, 'execute')

    def query(self, sql):
        try:
            if self.is_native:
                res = self.client.execute(sql, with_column_types=True)
                class ResultProxy:
                    def __init__(self, r, fixer):
                        self.result_rows = fixer(r[0])
                        self.column_names = [col[0] for col in r[1]]
                return ResultProxy(res, self._fix_encoding)
            else:
                res = self.client.query(sql)
                if hasattr(res, 'result_rows'):
                    # 修改原始对象的 result_rows
                    fixed_rows = self._fix_encoding(res.result_rows)
                    # 由于 result_rows 可能是只读或特殊序列，我们创建一个新对象包装它
                    class ConnectResultProxy:
                        def __init__(self, original, rows):
                            self.result_rows = rows
                            self.column_names = original.column_names
                    return ConnectResultProxy(res, fixed_rows)
                return res
        except Exception as e:
            logger.error(f"❌ [CharsetProxy] 查询执行失败: {e}")
            raise

    def _fix_encoding(self, rows):
        if not rows: return rows
        new_rows = []
        for row in rows:
            new_row = []
            for val in row:
                if isinstance(val, bytes):
                    try:
                        new_row.append(val.decode('utf-8'))
                    except UnicodeDecodeError:
                        det = chardet.detect(val)
                        enc = det['encoding'] or 'gbk'
                        new_row.append(val.decode(enc, errors='replace'))
                elif isinstance(val, str):
                    # 处理可能的二次编码错误 (Latin-1 错认)
                    try:
                        # 尝试检测是否是误用 latin-1 解码了 gbk
                        if any(ord(c) > 127 for c in val):
                            # 如果字符串中包含非 ASCII，尝试探测
                            pass 
                    except: pass
                    new_row.append(val)
                else:
                    new_row.append(val)
            new_rows.append(tuple(new_row))
        return new_rows

def get_clickhouse_client():
    global _CK_GLOBAL_CLIENT
    
    if _CK_GLOBAL_CLIENT:
        try:
            # 注意：Proxy 对象没有直接的 query 之外的方法，如果需要健康检查，需要穿透
            client_to_check = _CK_GLOBAL_CLIENT.client if hasattr(_CK_GLOBAL_CLIENT, 'client') else _CK_GLOBAL_CLIENT
            if hasattr(client_to_check, 'query'):
                client_to_check.query("SELECT 1")
            else:
                client_to_check.execute("SELECT 1")
            return _CK_GLOBAL_CLIENT
        except Exception:
            _CK_GLOBAL_CLIENT = None

    host = _os.getenv("CLICKHOUSE_HOST", "localhost")
    port = int(_os.getenv("CLICKHOUSE_PORT", "8123"))
    user = _os.getenv("CLICKHOUSE_USER", "default")
    password = _os.getenv("CLICKHOUSE_PASSWORD", "")

    # ── [V68.5] 物理自愈：尝试多种路径穿透网络阻断 ─────────────────────────
    client = None
    # 路径 1: 标准 localhost (已通过 NO_PROXY 保护)
    try:
        logger.info(f"🔌 [DB_CONN] 尝试路径 1: {host}:{port} (HTTP)...")
        client = clickhouse_connect.get_client(
            host=host, port=port, username=user, password=password,
            connect_timeout=5, send_receive_timeout=10
        )
        logger.success("✅ [DB_CONN] 路径 1 连接成功！")
    except Exception as e1:
        logger.warning(f"⚠️ [DB_CONN] 路径 1 失败: {e1}")

    # 路径 2: 探测 WSL2 虚拟 IP (针对 localhost 转发失效场景)
    if not client:
        try:
            import subprocess
            logger.info("🔌 [DB_CONN] 尝试路径 2: 探测 WSL IP 直连...")
            res = subprocess.run(["wsl", "hostname", "-I"], capture_output=True, text=True, timeout=3)
            wsl_ip = res.stdout.split()[0] if res.stdout else None
            if wsl_ip:
                logger.info(f"🔗 [DB_CONN] 发现 WSL IP: {wsl_ip}, 尝试连接...")
                client = clickhouse_connect.get_client(
                    host=wsl_ip, port=8123, username=user, password=password,
                    connect_timeout=5
                )
                logger.success(f"✅ [DB_CONN] 路径 2 ({wsl_ip}) 连接成功！")
        except Exception as e2:
            logger.warning(f"⚠️ [DB_CONN] 路径 2 失败: {e2}")

    # 路径 3: Fallback 到 Native 协议 (针对 8123 端口被深度劫持场景)
    if not client:
        try:
            logger.info("🔌 [DB_CONN] 尝试路径 3: 切换 Native 协议 (Port 9000)...")
            import clickhouse_driver
            client = clickhouse_driver.Client(host=host, port=9000, user=user, password=password)
            client.execute("SELECT 1")
            logger.success("✅ [DB_CONN] 路径 3 (Native 9000) 连接成功！")
        except Exception as e3:
            logger.error(f"❌ [DB_CONN] 所有路径均告失败。最后报错: {e3}")
            raise RuntimeError(f"无法建立 ClickHouse 连接。请检查服务是否开启或网络是否存在物理干扰。")

    _CK_GLOBAL_CLIENT = CharsetProxy(client)
    return _CK_GLOBAL_CLIENT

