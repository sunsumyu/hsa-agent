import os
import json
import time
import tempfile
import pytest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, MagicMock

from app.infra.db_conn import CharsetProxy
from app.infra.usage_tracker import UsageTracker

def test_native_driver_client_still_serializes_concurrent_access():
    """回归护栏：Native 客户端 (单 TCP 连接) 不可并发 — 必须互斥。

    无论驱动解锁与否 (方案1) 此契约不变; clickhouse_driver 在当前环境未安装,
    但代码路径必须保持安全。
    """
    class NativeOverlapDetectorClient:
        def __init__(self):
            self.running_count = 0
            self.max_overlap = 0

        def execute(self, sql, with_column_types=False):
            self.running_count += 1
            if self.running_count > self.max_overlap:
                self.max_overlap = self.running_count
            time.sleep(0.02)  # 模拟网络与数据库查询耗时
            self.running_count -= 1
            return [(1,)], [("val", "String")]  # Native 驱动行格式为 tuple

    raw_client = NativeOverlapDetectorClient()
    proxy = CharsetProxy(raw_client)

    # Native 分支必须持有并发互斥锁
    assert hasattr(proxy, "_lock"), "CharsetProxy 必须包含 _lock 保护底层 ClickHouse Socket"

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(proxy.query, f"SELECT {i}") for i in range(5)]
        for f in futures:
            res = f.result()
            assert res == [{"val": 1}]

    # 互斥断言：底层最大并发重叠数必须严格为 1，杜绝 Socket 冲突
    assert raw_client.max_overlap == 1


def test_http_client_is_not_globally_serialized():
    """反向验证 [方案1]：HTTP 客户端 (urllib3 连接池, 线程安全) 不得被全局锁串行化。

    生产环境 clickhouse_driver 未安装, CharsetProxy 永远包装的是
    clickhouse_connect HttpClient — 旧实现给自带连接池的线程安全客户端
    套全局互斥, 把 maxsize=8 的池串行成 1 条队, 纯损耗。
    旧实现: query 全程持锁 → max_overlap == 1 (必红)。
    新实现: 并发真实重叠 → max_overlap >= 2 (绿)。
    """
    class HTTPOverlapDetectorClient:
        def __init__(self):
            self.running_count = 0
            self.max_overlap = 0

        def query(self, sql):
            self.running_count += 1
            if self.running_count > self.max_overlap:
                self.max_overlap = self.running_count
            time.sleep(0.1)  # 模拟网络往返, 睡眠释放 GIL 保证真实重叠
            self.running_count -= 1
            return [{"val": 1}]

    raw_client = HTTPOverlapDetectorClient()
    proxy = CharsetProxy(raw_client)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(proxy.query, f"SELECT {i}") for i in range(8)]
        for f in futures:
            assert f.result(timeout=10) == [{"val": 1}]

    assert raw_client.max_overlap >= 2, (
        "HTTP 客户端被全局锁串行化 (max_overlap=1): 自带连接池的线程安全客户端被白白排队"
    )


def test_usage_tracker_concurrent_records_and_atomic_save():
    """RED 测试：UsageTracker 必须具备线程安全锁保护与 os.replace 原子落盘，防止指标被覆盖与半包写入"""
    with tempfile.TemporaryDirectory() as tmpdir:
        stats_file = os.path.join(tmpdir, "usage_stats.json")
        tracker = UsageTracker(stats_path=stats_file)

        # 必须持有并发互斥锁
        assert hasattr(tracker, "_lock"), "UsageTracker 必须包含 _lock 保护全局度量字典"

        replace_called = []
        orig_replace = os.replace
        def mock_replace(src, dst):
            replace_called.append((src, dst))
            return orig_replace(src, dst)

        with patch("os.replace", side_effect=mock_replace):
            def record_task(idx):
                tracker.record_usage(
                    model_id="test-model",
                    input_tokens=10,
                    output_tokens=20,
                    latency_ms=15.0
                )

            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(record_task, range(20)))

        # 1. 累加准确性断言 (20 次 * (10+20) = 600)
        assert tracker.stats.daily_usage["test-model"] == 600
        assert tracker.stats.daily_requests["test-model"] == 20

        # 2. 原子落盘断言
        assert len(replace_called) >= 1
        assert os.path.exists(stats_file)
        with open(stats_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert data["daily_usage"]["test-model"] == 600
