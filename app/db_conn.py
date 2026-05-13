"""
app/db_conn.py
==============
[V111.0] ClickHouse 连接管理：增强型编码代理 + 物理自愈路径
"""
import os as _os
import clickhouse_connect
from loguru import logger

# [V68.1] 代理穿透：强制禁用针对 localhost 的代理拦截
_os.environ['NO_PROXY'] = 'localhost,127.0.0.1,::1'
_os.environ['no_proxy'] = 'localhost,127.0.0.1,::1'

_CK_GLOBAL_CLIENT = None

class SqlExecError(Exception):
    """
    [V131.0] 结构化 SQL 执行异常。
    与普通 Exception 区分，便于上层调用方单一来源地记录日志，
    避免同一错误在多个层次重复输出。
    """
    pass


class CharsetProxy:
    """[V111.0] 工业级编码代理：确保 ClickHouse 返回的数据在任何环境下均为干净的 UTF-8。
    
    解决 Windows/Linux 混合环境下的 GBK 编码冲突，并自动适配 HTTP (clickhouse-connect) 
    和 Native (clickhouse-driver) 两种驱动的输出格式。
    """
    def __init__(self, client):
        self.client = client

    def _normalize_item(self, item):
        """递归清理并标准化数据编码"""
        if isinstance(item, str):
            try:
                # 尝试修复可能的编码错乱 (例如 ClickHouse 返回了原始 GBK 字节码但被误认为 latin1)
                return item.encode('latin1').decode('gbk')
            except (UnicodeEncodeError, UnicodeDecodeError):
                # 已经是 UTF-8 或无法修复，直接返回清理后的字符串，忽略非法字符
                try:
                    return item.encode('utf-8', 'ignore').decode('utf-8')
                except:
                    return str(item)
        elif isinstance(item, list):
            return [self._normalize_item(i) for i in item]
        elif isinstance(item, dict):
            return {k: self._normalize_item(v) for k, v in item.items()}
        elif isinstance(item, tuple):
            return tuple(self._normalize_item(i) for i in item)
        return item

    def _clean_error_message(self, msg: str) -> str:
        """[V119.0] 物理截断：切除 ClickHouse 冗长的 C++ 堆栈信息，只保留核心错误提示。"""
        if not msg: return ""
        # 寻找 Stack trace: 标记并截断，剔除大量无意义的 C++ 指针信息
        marker = "Stack trace:"
        if marker in msg:
            msg = msg.split(marker)[0].strip()
        return msg

    def query(self, sql):
        """执行 SQL 并返回标准化结果列表 (List[Dict])"""
        try:
            # 1. 物理执行并统一格式
            if hasattr(self.client, 'query'): # HTTP Client
                res = self.client.query(sql)
                # 兼容不同版本的返回对象
                if hasattr(res, 'result_rows') and hasattr(res, 'column_names'):
                    columns = [c[0] if isinstance(c, tuple) else c for c in res.column_names]
                    data = [dict(zip(columns, row)) for row in res.result_rows]
                elif isinstance(res, list):
                    data = res
                else:
                    # 兜底：如果无法识别结果格式
                    data = []
            else: # Native Client
                rows, columns = self.client.execute(sql, with_column_types=True)
                col_names = [c[0] for c in columns]
                data = [dict(zip(col_names, row)) for row in rows]
            
            # 2. 编码标准化引擎
            return self._normalize_item(data)
            
        except Exception as e:
            clean_msg = self._clean_error_message(str(e))
            # [V131.0] 日志去重治理：层级分流原则——此处不再打印 ERROR，改为抛出结构化异常
            # 由上层的调用方（tools.py）統一记录日志，避免同一错误被打印多次
            raise SqlExecError(clean_msg)

    def execute(self, sql, *args, **kwargs):
        """兼容性接口：映射到 query"""
        return self.query(sql)

def get_clickhouse_client():
    global _CK_GLOBAL_CLIENT
    
    if _CK_GLOBAL_CLIENT:
        try:
            # 健康检查
            client_to_check = _CK_GLOBAL_CLIENT.client if hasattr(_CK_GLOBAL_CLIENT, 'client') else _CK_GLOBAL_CLIENT
            if hasattr(client_to_check, 'execute'): # Native
                client_to_check.execute("SELECT 1")
            else:
                client_to_check.query("SELECT 1")
            return _CK_GLOBAL_CLIENT
        except Exception:
            _CK_GLOBAL_CLIENT = None

    host = _os.getenv("CLICKHOUSE_HOST", "localhost")
    user = _os.getenv("CLICKHOUSE_USER", "default")
    password = _os.getenv("CLICKHOUSE_PASSWORD", "")

    # ── [V110.6] 物理自愈：优先使用 Native 协议（Port 9000） ──────────────────
    client = None
    
    # 路径 1: Native 协议 (Port 9000) - 经测试在该环境最稳定，避开 8123 端口冲突
    try:
        logger.info(f"🔌 [DB_CONN] 路径 1: 尝试 Native 协议 ({host}:9000)...")
        import clickhouse_driver
        client = clickhouse_driver.Client(
            host=host, port=9000, user=user, password=password,
            connect_timeout=5, send_receive_timeout=10
        )
        client.execute("SELECT 1")
        logger.success("✅ [DB_CONN] 路径 1 (Native 9000) 连接成功！")
    except Exception as e1:
        logger.warning(f"⚠️ [DB_CONN] 路径 1 (Native) 失败: {e1}")
        client = None

    # 路径 2: 探测 WSL IP (HTTP 8123)
    if not client:
        try:
            import subprocess
            logger.info("🔌 [DB_CONN] 路径 2: 探测 WSL IP 直连 (HTTP)...")
            res = subprocess.run(["wsl", "hostname", "-I"], capture_output=True, text=True, timeout=3)
            wsl_ips = res.stdout.split() if res.stdout else []
            for wsl_ip in wsl_ips:
                try:
                    logger.info(f"🔗 [DB_CONN] 尝试连接 WSL IP: {wsl_ip}")
                    client = clickhouse_connect.get_client(
                        host=wsl_ip, port=8123, username=user, password=password,
                        connect_timeout=3
                    )
                    logger.success(f"✅ [DB_CONN] 路径 2 ({wsl_ip}) 连接成功！")
                    break
                except Exception: continue
        except Exception as e_wsl:
            logger.warning(f"⚠️ [DB_CONN] 路径 2 (WSL IP) 探测失败: {e_wsl}")

    # 路径 3: 标准 localhost (HTTP 8123)
    if not client:
        try:
            logger.info(f"🔌 [DB_CONN] 路径 3: localhost:8123 (HTTP)...")
            client = clickhouse_connect.get_client(
                host='localhost', port=8123, username=user, password=password,
                connect_timeout=3
            )
            client.query("SELECT 1")
            logger.success("✅ [DB_CONN] 路径 3 连接成功！")
        except Exception as e3:
            logger.error(f"❌ [DB_CONN] 所有路径均告失败。最后报错: {e3}")
            raise RuntimeError(f"无法建立 ClickHouse 连接。请检查服务是否开启。")

    _CK_GLOBAL_CLIENT = CharsetProxy(client)
    return _CK_GLOBAL_CLIENT
