"""
tests/unit/core/test_container_lifecycle_deep_red.py
===================================================
[TDD Red -> Green] DI Container 完备性审计与生命周期收口测试：
1. LazyProxy 动态穿透契约 (ServiceProvider.override 即使在首次调用后也能立即生效)
2. ServiceProvider.clear_overrides 与 clear_instances 细粒度隔离
3. ServiceProvider.dispose_all 资源优雅释放 (支持 close / dispose / shutdown)
4. ServiceProvider.get_status 服务诊断矩阵 (active / pending / overridden)
"""

import pytest
from unittest.mock import MagicMock
from app.core.container import ServiceProvider, LazyProxy


class SampleDisposableService:
    def __init__(self):
        self.closed = False
        self.call_count = 0

    def query(self) -> str:
        self.call_count += 1
        return f"result_{self.call_count}"

    def close(self):
        self.closed = True


class SampleShutdownService:
    def __init__(self):
        self.shutdown_called = False

    def shutdown(self):
        self.shutdown_called = True


@pytest.fixture(autouse=True)
def clean_test_di():
    ServiceProvider.clear_overrides()
    ServiceProvider.clear_instances()
    yield
    ServiceProvider.clear_overrides()
    ServiceProvider.clear_instances()


def test_lazy_proxy_dynamic_override_transparency():
    """
    验证核心设计缺陷修复：
    LazyProxy 在首次访问后，若外部发生 ServiceProvider.override，必须无缝穿透生效！
    """
    ServiceProvider.register("dynamic_svc", SampleDisposableService)
    proxy = LazyProxy("dynamic_svc")

    # 1. 首次访问真实实例
    res1 = proxy.query()
    assert res1 == "result_1"

    # 2. 外部注入 Mock
    mock_svc = MagicMock()
    mock_svc.query.return_value = "mocked_query"
    ServiceProvider.override("dynamic_svc", mock_svc)

    # 3. 验证 LazyProxy 穿透更新
    assert proxy.query() == "mocked_query"

    # 4. 清除 override 后自动回退
    ServiceProvider.clear_overrides()
    assert proxy.query() == "result_2"


def test_clear_instances_recreates_singleton():
    """验证 clear_instances 会清空缓存实例，但保留注册工厂"""
    ServiceProvider.register("recreate_svc", SampleDisposableService)
    inst1 = ServiceProvider.resolve("recreate_svc")
    assert ServiceProvider.resolve("recreate_svc") is inst1

    ServiceProvider.clear_instances()
    inst2 = ServiceProvider.resolve("recreate_svc")
    assert inst2 is not inst1
    assert isinstance(inst2, SampleDisposableService)


def test_dispose_all_lifecycle():
    """验证 dispose_all 会调用所有已实例化服务的 close/shutdown/dispose 钩子"""
    ServiceProvider.register("svc_close", SampleDisposableService)
    ServiceProvider.register("svc_shutdown", SampleShutdownService)
    ServiceProvider.register("svc_uninstantiated", SampleDisposableService)

    # 只实例化前两个
    s1 = ServiceProvider.resolve("svc_close")
    s2 = ServiceProvider.resolve("svc_shutdown")

    assert not s1.closed
    assert not s2.shutdown_called

    # 触发容器销毁
    ServiceProvider.dispose_all()

    assert s1.closed
    assert s2.shutdown_called


def test_get_status_matrix():
    """验证 get_status 能正确诊断已激活与未激活服务"""
    ServiceProvider.register("active_svc", SampleDisposableService)
    ServiceProvider.register("pending_svc", SampleShutdownService)

    # 实例化 active_svc
    ServiceProvider.resolve("active_svc")
    # 覆盖 pending_svc
    ServiceProvider.override("pending_svc", MagicMock())

    status = ServiceProvider.get_status()
    assert "active_svc" in status
    assert status["active_svc"]["status"] == "active"
    assert status["active_svc"]["is_overridden"] is False

    assert "pending_svc" in status
    assert status["pending_svc"]["is_overridden"] is True
