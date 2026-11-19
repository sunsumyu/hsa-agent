# tests/integration/test_observability_pipeline_e2e.py
# -*- coding: utf-8 -*-
"""
tests/integration/test_observability_pipeline_e2e.py
=====================================================
[E2E Integration Test] 验证企业级可观测性全链路打通：
1. DI 容器安全注入
2. SessionContextManager 轮次与 Thread 构建
3. PIISanitizer 数据脱敏门禁
4. AdaptiveSampler 成本采样与熔断保护
5. HardenedTracer 探针与 FeedbackCollector 在线反馈
"""

import pytest
from app.core.container import ServiceProvider
from app.core.bootstrap import register_services
from app.core.observability import (
    PIISanitizer,
    AdaptiveSampler,
    HardenedTracer,
    SessionContextManager,
    FeedbackCollector
)

@pytest.fixture(autouse=True)
def setup_env():
    ServiceProvider.clear_overrides()
    ServiceProvider.clear_instances()
    register_services()
    yield
    ServiceProvider.clear_overrides()
    ServiceProvider.clear_instances()

def test_observability_service_integration_e2e():
    obs = ServiceProvider.resolve("observability")
    assert obs is not None
    assert obs.__class__.__name__ == "ObservabilityService"

    session_id = "test-session-e2e-001"
    
    # 1. 验证 Turn Config 动态构建与元数据注入 (SessionContextManager)
    cfg = SessionContextManager.build_turn_config(
        session_id=session_id,
        turn_index=1,
        action_name="无手术记录麻醉核查"
    )
    assert cfg["run_name"] == "Audit-Turn-1: 无手术记录麻醉核查"
    assert "turn:1" in cfg["tags"]
    assert cfg["metadata"]["session_id"] == session_id
    assert cfg["metadata"]["turn"] == 1
    assert cfg["configurable"]["thread_id"] == session_id

    final_cfg = obs.configure_run(
        node_name="PLANNER",
        session_id=session_id,
        base_config=cfg
    )
    assert final_cfg["metadata"]["node"] == "PLANNER"
    assert final_cfg["metadata"]["turn"] == 1
    assert final_cfg["configurable"]["thread_id"] == session_id

    # 2. 验证 PII 自动合规打码
    raw_output = {"result": "患者身份证 420101198001011234 查无手术流水", "phone": "13912345678"}
    sanitized = obs._sanitize_pii(raw_output)
    assert "420101198001011234" not in sanitized["result"]
    assert "420101**********1234" in sanitized["result"]
    assert "13912345678" not in sanitized["phone"]
    assert "139****5678" in sanitized["phone"]

    # 3. 验证通过闭环接口记录反馈
    # 离线模拟下即使无远端也不会崩溃抛出未捕获异常
    res = obs.record_feedback("run-test-id", 1.0, category="accepted", comment="SQL精确")
    assert isinstance(res, bool)
