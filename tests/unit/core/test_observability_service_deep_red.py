# -*- coding: utf-8 -*-
"""
tests/unit/core/test_observability_service_deep_red.py
======================================================
[TDD Red -> Green] 统一企业级可观测深模块 (ObservabilityService) 架构契约测试
Driven by: Matt Pocock Deep Module Principles (Codebase Design)

严格断言：
1. 接口小而深 (Small Interface, Deep Implementation) - 契约方法收敛
2. 完全受控于 ServiceProvider DI 容器，支持生命周期 dispose_all()
3. 医保与金融 PII 敏感隐私数据在离开进程前自动脱敏
4. 两个适配器法则 (Two-Adapter Rule)：内存 Fake 测试无网络开销
5. 节点作用域管理 (node_scope) 治理 LangGraph 嵌套调用
6. 向后兼容层 (Backward-Compatible Aliasing) 零破坏平滑过渡
"""

import pytest
from app.core.container import ServiceProvider
from app.core.bootstrap import register_services


@pytest.fixture(autouse=True)
def clean_di_state():
    """每次测试前后保持干净的 DI 环境"""
    ServiceProvider.clear_overrides()
    ServiceProvider.clear_instances()
    register_services()
    yield
    ServiceProvider.clear_overrides()
    ServiceProvider.clear_instances()


def test_observability_registered_in_di():
    """断言 1: 可观测服务必须已作为基础设施受管单例注册在 ServiceProvider"""
    obs = ServiceProvider.resolve("observability")
    assert obs is not None
    assert obs.__class__.__name__ == "ObservabilityService"


def test_minimal_interface_surface():
    """断言 2: [小接口] 对外仅暴露最小受敛接缝，严禁杂乱散落或泄漏第三方 Client"""
    obs = ServiceProvider.resolve("observability")

    required_methods = [
        "configure_run",
        "get_stream_callbacks",
        "record_feedback",
        "shutdown",
        "node_scope",
    ]
    for method_name in required_methods:
        assert hasattr(obs, method_name), f"深模块缺失核心契约接口: {method_name}"

    # 严禁将第三方 SDK client 作为公共契约直接对外暴漏
    assert not hasattr(obs, "client"), "严禁将第三方 client 直接作为外部公开属性暴露！"


def test_pii_auto_masking():
    """断言 3: [合规脱敏] 医保 PII 敏感信息在离开进程前自动打码脱敏"""
    obs = ServiceProvider.resolve("observability")

    raw_payload = {
        "patient_name": "张三",
        "id_card": "110101199003072345",
        "phone": "13800138000",
        "med_card": "6222021234567890123",
        "amount": 6056.09,
        "token": "sk-secret-token-12345"
    }

    assert hasattr(obs, "_sanitize_pii"), "深模块必须内置 _sanitize_pii 静态/私有脱敏管道"
    sanitized = obs._sanitize_pii(raw_payload)

    # 敏感信息必须被打码
    assert "110101199003072345" not in str(sanitized)
    assert "13800138000" not in str(sanitized)
    assert "6222021234567890123" not in str(sanitized)
    assert "sk-secret-token-12345" not in str(sanitized)
    # 数值指标与非敏感文本完整保留
    assert sanitized["amount"] == 6056.09
    assert sanitized["patient_name"] == "张三"


def test_two_adapters_rule_with_fake():
    """断言 4: [两个适配器法则] 支持在测试中使用零网络开销的内存 Fake"""
    class InMemoryObservabilityFake:
        def __init__(self):
            self.feedbacks = []
            self.closed = False

        def get_stream_callbacks(self):
            return []

        def configure_run(self, node_name: str, session_id: str, extra_meta=None, base_config=None):
            cfg = (base_config or {}).copy()
            cfg["callbacks"] = []
            cfg["metadata"] = {"node": node_name, "session_id": session_id, **(extra_meta or {})}
            return cfg

        def record_feedback(self, run_id: str, score: float, category=None, comment=None):
            self.feedbacks.append({"run_id": run_id, "score": score, "comment": comment})
            return True

        def shutdown(self):
            self.closed = True

    fake_instance = InMemoryObservabilityFake()
    ServiceProvider.override("observability", fake_instance)

    resolved = ServiceProvider.resolve("observability")
    assert resolved is fake_instance

    ok = resolved.record_feedback("run-10086", 1.0, comment="保妇康栓违规命中")
    assert ok is True
    assert len(fake_instance.feedbacks) == 1
    assert fake_instance.feedbacks[0]["run_id"] == "run-10086"

    # 验证适配器具备契约 shutdown 能力
    resolved.shutdown()
    assert fake_instance.closed is True


def test_node_scope_governance():
    """断言 5: [作用域管理] node_scope 统筹图节点生命周期与 Trace 元数据"""
    obs = ServiceProvider.resolve("observability")

    state = {"session_id": "session-audit-99", "retry_count": 1}
    with obs.node_scope("PLANNER", "session-audit-99", state) as meta:
        assert meta["langgraph_node"] == "PLANNER"
        assert meta["session_id"] == "session-audit-99"
        assert meta["retry_count"] == 1


def test_backward_compatibility_layer():
    """断言 6: [向后兼容别名] 旧模块函数调用透明委托至 DI 容器，零破坏"""
    from app.core.observability import init_observability, get_callbacks, build_obs_config

    obs = init_observability()
    assert obs is not None

    callbacks = get_callbacks()
    assert isinstance(callbacks, list)

    config = build_obs_config({}, "TEST_NODE", {"session_id": "sess-test", "retry_count": 0})
    assert "metadata" in config
    assert config["metadata"]["node"] == "TEST_NODE"
    assert config["metadata"]["session_id"] == "sess-test"
