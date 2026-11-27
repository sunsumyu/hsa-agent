"""
app/db_conn.py
==============
[V111.0] ClickHouse 连接管理：增强型编码代理 + 物理自愈路径
"""
import threading
import time

import os as _os
import clickhouse_connect
from loguru import logger

# [V68.1] 代理穿透：强制禁用针对 localhost 的代理拦截
_os.environ['NO_PROXY'] = 'localhost,127.0.0.1,::1'
_os.environ['no_proxy'] = 'localhost,127.0.0.1,::1'

_CK_GLOBAL_CLIENT = None
# [P1-5] 建连互斥: 该函数被 asyncio.to_thread 的 SQL 路径并发调用,
# 并发首次建连必须只允许一条线程执行完整探测链, 否则各自建 CharsetProxy
# 后互相覆盖 → 连接泄漏。
# 快路径不持此锁, 保持已建连时零开销。
_CK_CREATE_LOCK = threading.Lock()
# [方案4] 建连失败冷却: 服务下线期间快速失败, 杜绝各线程串行重建风暴
_CK_LAST_BUILD_FAIL_TS = 0.0
_CK_BUILD_COOLDOWN_S = 5.0

# [方案4] 仅传输层故障触发重建+重试; 服务端已应答的错误 (语法/权限等)
# 重连毫无意义, 反而让每条坏 SQL 白付一次探测链 (WSL 子进程探活最贵 3s)。
# 指纹保守匹配: 漏配的传输错误仅退化为"不重试", 不会误伤服务端错误。
_TRANSPORT_ERROR_FINGERPRINTS = (
    "executing http request attempt",  # clickhouse-connect 传输层统一报错入口
    "max retries exceeded",            # urllib3 连接池重试耗尽
    "failed to establish",             # WinError 10061 底层文本
    "connection refused",
    "connection reset",
    "connection aborted",
    "broken pipe",
    "connection timed out",
    "timed out",
    "unreachable",
    "getaddrinfo failed",
)


def _is_transport_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(f in msg for f in _TRANSPORT_ERROR_FINGERPRINTS)

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

    并发契约 [方案1] 按驱动分流:
      - HTTP 客户端 (clickhouse-connect): 底层为 urllib3 连接池, 线程安全,
        不做全局串行, 并发度 = 池 maxsize;
      - Native 客户端 (clickhouse-driver): 单 TCP 连接不可并发, 穿透全程互斥。
    自愈契约 [方案4]: 查询遇传输层故障 → 单飞重建 + 重试一次, 调用方无感;
    服务端拒绝 (语法/权限等) 不重建不重试, 直接 SqlExecError。
    """
    def __init__(self, client):
        self.client = client
        self._is_http = hasattr(client, "query")  # HTTP 走 query, Native 走 execute
        self._lock = threading.Lock()  # 仅 Native 分支使用

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
                except Exception:
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

    def _raw_query(self, sql):
        """驱动分发并取出原始行数据 (不含编码标准化)。"""
        if self._is_http:
            res = self.client.query(sql)
            # 兼容不同版本的返回对象
            if hasattr(res, 'result_rows') and hasattr(res, 'column_names'):
                columns = [c[0] if isinstance(c, tuple) else c for c in res.column_names]
                return [dict(zip(columns, row)) for row in res.result_rows]
            if isinstance(res, list):
                return res
            # 兜底：如果无法识别结果格式
            return []
        with self._lock:
            rows, columns = self.client.execute(sql, with_column_types=True)
            col_names = [c[0] for c in columns]
            return [dict(zip(col_names, row)) for row in rows]

    def query(self, sql, _selfheal_retried: bool = False):
        """执行 SQL 并返回标准化结果列表 (List[Dict])。

        自愈契约 [方案4]: 传输层故障 → 单飞重建 + 重试一次, 调用方无感;
        服务端拒绝 (语法/权限等) 不重建不重试, 直接 SqlExecError。
        """
        try:
            data = self._raw_query(sql)
        except Exception as e:
            if not _is_transport_error(e) or _selfheal_retried:
                raise SqlExecError(self._clean_error_message(str(e))) from e
            try:
                fresh = _rebuild_after_failure(self)
            except Exception as rebuild_err:
                raise SqlExecError(self._clean_error_message(str(e))) from rebuild_err
            return fresh.query(sql, _selfheal_retried=True)
        # 编码标准化在锁外执行 (纯 CPU 转换, 不触碰连接)
        return self._normalize_item(data)

    def execute(self, sql, *args, **kwargs):
        """兼容性接口：映射到 query"""
        return self.query(sql)

    def command(self, sql):
        """[V185.0] 驱动无关命令接口：自动兼容 Native (driver) 和 HTTP (connect) 执行 DDL"""
        try:
            if self._is_http:
                return self.client.command(sql)
            with self._lock:
                return self.client.execute(sql)
        except Exception as e:
            if _is_transport_error(e):
                self._refresh_after_failure_quietly()
            raise SqlExecError(self._clean_error_message(str(e))) from e

    def insert(self, table, data, column_names=None):
        """[V185.0] 驱动无关数据批量导入接口：自动兼容 Native 和 HTTP 插入临时表"""
        try:
            if self._is_http:
                return self.client.insert(table, data, column_names=column_names)
            with self._lock:
                cols = f"({', '.join(column_names)})" if column_names else ""
                sql = f"INSERT INTO {table} {cols} VALUES"
                return self.client.execute(sql, data)
        except Exception as e:
            if _is_transport_error(e):
                self._refresh_after_failure_quietly()
            raise SqlExecError(self._clean_error_message(str(e))) from e

    def _refresh_after_failure_quietly(self):
        """非查询路径失败后尽力刷新全局客户端 (不重试当前操作, 写入非幂等)。"""
        try:
            _rebuild_after_failure(self)
        except Exception as exc:
            logger.debug(f"[DB_CONN] Quiet client refresh failed: {exc}")

def _make_http_pool():
    """[方案1] 显式 HTTP 连接池。

    maxsize=16 覆盖突发并发 (调用方为 asyncio.to_thread 线程池 + 后台工作线程);
    block=True 让超额请求排队, 而非 urllib3 默认 block=False 的新建即弃 (连接 churn)。
    构建失败返回 None, 走驱动默认池 (maxsize=8)。
    """
    try:
        from urllib3.poolmanager import PoolManager
        from clickhouse_connect.driver.httputil import get_pool_manager_options
        return PoolManager(**get_pool_manager_options(maxsize=16, block=True))
    except Exception as e:
        logger.warning(f"⚠️ [DB_CONN] 自定义连接池构建失败, 使用驱动默认池: {e}")
        return None


def _try_connect_native(host: str, user: str, password: str, database: str, readonly_val: int):
    """路径 1: Native 协议 (Port 9000) 探测与连接。"""
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            if s.connect_ex((host, 9000)) != 0:
                logger.debug(f"[DB_CONN] 跳过路径 1: {host}:9000 未开放")
                return None
            logger.info(f"🔌 [DB_CONN] 路径 1: 尝试 Native 协议 ({host}:9000)...")
            import clickhouse_driver

            client = clickhouse_driver.Client(
                host=host,
                port=9000,
                user=user,
                password=password,
                database=database,
                connect_timeout=3,
                send_receive_timeout=5,
                settings={"readonly": readonly_val},
            )
            client.execute("SELECT 1")
            logger.success("✅ [DB_CONN] 路径 1 (Native 9000) 连接成功！")
            return client
    except Exception as e1:
        logger.warning(f"⚠️ [DB_CONN] 路径 1 (Native) 失败: {e1}")
        return None


def _try_connect_wsl_http(user: str, password: str, database: str, readonly_val: int):
    """路径 2: 探测 WSL IP 直连 HTTP (Port 8123)。"""
    try:
        import subprocess

        logger.info("🔌 [DB_CONN] 路径 2: 探测 WSL IP 直连 (HTTP)...")
        res = subprocess.run(["wsl", "hostname", "-I"], capture_output=True, text=True, timeout=3)
        for wsl_ip in (res.stdout.split() if res.stdout else []):
            try:
                logger.info(f"🔗 [DB_CONN] 尝试连接 WSL IP: {wsl_ip}")
                client = clickhouse_connect.get_client(
                    host=wsl_ip,
                    port=8123,
                    username=user,
                    password=password,
                    database=database,
                    connect_timeout=3,
                    settings={"readonly": readonly_val},
                    pool_mgr=_make_http_pool(),
                )
                logger.success(f"✅ [DB_CONN] 路径 2 ({wsl_ip}) 连接成功！")
                return client
            except Exception:
                continue
    except Exception as e_wsl:
        logger.warning(f"⚠️ [DB_CONN] 路径 2 (WSL IP) 探测失败: {e_wsl}")
    return None


def _connect_localhost_http(user: str, password: str, database: str, readonly_val: int):
    """路径 3: 标准 localhost HTTP 回退连接。"""
    http_port = int(_os.getenv("CLICKHOUSE_HTTP_PORT", _os.getenv("CLICKHOUSE_PORT", "8223")))
    try:
        logger.info(f"🔌 [DB_CONN] 路径 3: localhost:{http_port} (HTTP)...")
        client = clickhouse_connect.get_client(
            host='localhost',
            port=http_port,
            username=user,
            password=password,
            database=database,
            connect_timeout=3,
            settings={"readonly": readonly_val},
            pool_mgr=_make_http_pool(),
        )
        client.query("SELECT 1")
        logger.success("✅ [DB_CONN] 路径 3 连接成功！")
        return client
    except Exception as e3:
        logger.error(f"❌ [DB_CONN] 所有路径均告失败。最后报错: {e3}")
        raise RuntimeError("无法建立 ClickHouse 连接。请检查服务是否开启。")


def _build_raw_client():
    """三路径探测链 (Native 9000 → WSL HTTP → localhost HTTP), 返回已验证的原始客户端。"""
    global _CK_LAST_BUILD_FAIL_TS
    if time.time() - _CK_LAST_BUILD_FAIL_TS < _CK_BUILD_COOLDOWN_S:
        raise RuntimeError(
            f"ClickHouse 建连失败后处于 {_CK_BUILD_COOLDOWN_S:.0f}s 冷却窗口内, 拒绝重建。"
        )

    try:
        host = _os.getenv("CLICKHOUSE_HOST", "localhost")
        user = _os.getenv("CLICKHOUSE_USER", "default")
        password = _os.getenv("CLICKHOUSE_PASSWORD", "")
        database = _os.getenv("CLICKHOUSE_DB", "default")
        readonly_val = 0 if _os.getenv("ARGUS_DB_READWRITE") == "true" else 1

        client = (
            _try_connect_native(host, user, password, database, readonly_val)
            or _try_connect_wsl_http(user, password, database, readonly_val)
            or _connect_localhost_http(user, password, database, readonly_val)
        )
        _CK_LAST_BUILD_FAIL_TS = 0.0
        return client
    except Exception:
        _CK_LAST_BUILD_FAIL_TS = time.time()
        raise


def _rebuild_after_failure(stale_proxy: "CharsetProxy") -> "CharsetProxy":
    """[方案4] 传输层故障后的单飞重建。

    并发语义: 多线程同时失败时, 只有第一个持 _CK_CREATE_LOCK 的线程执行
    完整探测链, 其余线程直接采用刚重建的新客户端; 冷却窗口内快速失败。
    """
    global _CK_GLOBAL_CLIENT
    with _CK_CREATE_LOCK:
        if _CK_GLOBAL_CLIENT is not None and _CK_GLOBAL_CLIENT is not stale_proxy:
            return _CK_GLOBAL_CLIENT  # 其它线程刚完成重建, 直接采用
        fresh = CharsetProxy(_build_raw_client())
        _CK_GLOBAL_CLIENT = fresh
        return fresh


def get_clickhouse_client():
    """获取全局 ClickHouse 客户端 (单例)。

    并发语义 (P1-5): 快路径无锁直返; 仅创建路径持 _CK_CREATE_LOCK 互斥,
    锁内二次检查避免等锁线程重复建连。
    懒校验 [方案4]: 快路径不再每次执行 SELECT 1 探活 (省一半 RTT);
    连接失效由 CharsetProxy 在查询失败时单飞重建并重试一次, 调用方无感。
    """
    global _CK_GLOBAL_CLIENT

    if _CK_GLOBAL_CLIENT:
        return _CK_GLOBAL_CLIENT

    with _CK_CREATE_LOCK:
        # 双重检查: 等锁期间可能已有其它线程完成建连
        if _CK_GLOBAL_CLIENT:
            return _CK_GLOBAL_CLIENT
        fresh = CharsetProxy(_build_raw_client())
        _CK_GLOBAL_CLIENT = fresh
        return fresh
