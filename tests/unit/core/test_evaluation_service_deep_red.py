# -*- coding: utf-8 -*-
"""
tests/unit/core/test_evaluation_service_deep_red.py
===================================================
[TDD Red -> Green] 自动化回归评测深模块 (AuditEvaluationService) 契约测试
Driven by: Matt Pocock Deep Module Principles

测试项：
1. 注册于 ServiceProvider DI 容器，实现懒加载
2. 最小接口契约：对外仅暴露 evaluate_dataset, evaluate_local_dataset, sync_dataset_to_langsmith
3. 纯本地/离线计算打分逻辑验证 (SQL 合规率、违规金额偏差、用例达标门禁)
4. 真实本地黄金数据集 (tests/eval/golden_dataset.json) 全量脱机回归评测
5. 本地用例集同步上传至云端 LangSmith 数据集协议验证
"""

from unittest.mock import MagicMock
import pytest
from app.core.container import ServiceProvider
from app.core.bootstrap import register_services


@pytest.fixture(autouse=True)
def clean_di():
    ServiceProvider.clear_overrides()
    ServiceProvider.clear_instances()
    register_services()
    yield
    ServiceProvider.clear_overrides()
    ServiceProvider.clear_instances()


def test_evaluation_service_registered_in_di():
    """断言 1: 自动化评测服务必须注册在 DI 容器中"""
    eval_svc = ServiceProvider.resolve("evaluation_service")
    assert eval_svc is not None
    assert eval_svc.__class__.__name__ == "AuditEvaluationService"


def test_evaluation_service_interface_surface():
    """断言 2: [小接口] 外部仅调用评测核心接口，杜绝泄露第三方 SDK"""
    eval_svc = ServiceProvider.resolve("evaluation_service")
    assert hasattr(eval_svc, "evaluate_dataset")
    assert hasattr(eval_svc, "evaluate_local_dataset")
    assert hasattr(eval_svc, "sync_dataset_to_langsmith")
    assert hasattr(eval_svc, "score_prediction")
    assert not hasattr(eval_svc, "client")


def test_score_prediction_offline_logic():
    """断言 3: 内部私有打分器对 SQL 语法与物理违规金额的评分准确性"""
    eval_svc = ServiceProvider.resolve("evaluation_service")

    # 场景 A: SQL 正确且金额与真值完全吻合
    pred_perfect = {
        "final_sql": "SELECT * FROM fqz_fymx_test WHERE drug_name LIKE '%保妇康栓%'",
        "audit_result": {"total_amount": 6056.09, "record_count": 217}
    }
    truth_perfect = {"amount": 6056.09, "records": 217}
    scores_a = eval_svc.score_prediction(pred_perfect, truth_perfect)
    assert scores_a["sql_valid"] == 1.0
    assert scores_a["amount_match"] == 1.0
    assert scores_a["is_passing"] is True

    # 场景 B: SQL 语法非法 (不是以 SELECT 开头)
    pred_bad_sql = {
        "final_sql": "DROP TABLE fqz_fymx_test;",
        "audit_result": {"total_amount": 0.0, "record_count": 0}
    }
    scores_b = eval_svc.score_prediction(pred_bad_sql, truth_perfect)
    assert scores_b["sql_valid"] == 0.0
    assert scores_b["is_passing"] is False

    # 场景 C: 金额偏差超过 10% 阈值
    pred_bad_amt = {
        "final_sql": "SELECT * FROM fqz_fymx_test",
        "audit_result": {"total_amount": 1000.0, "record_count": 50}
    }
    scores_c = eval_svc.score_prediction(pred_bad_amt, truth_perfect)
    assert scores_c["sql_valid"] == 1.0
    assert scores_c["amount_match"] < 0.5
    assert scores_c["is_passing"] is False


def test_evaluate_local_dataset_offline():
    """断言 4: [脱机 CI 门禁] 直接对 tests/eval/golden_dataset.json 进行脱机回归验证"""
    eval_svc = ServiceProvider.resolve("evaluation_service")

    summary = eval_svc.evaluate_local_dataset("tests/eval/golden_dataset.json")
    assert summary.total_examples == 5
    assert summary.sql_accuracy == 1.0
    assert summary.amount_precision == 1.0
    assert summary.is_passing is True
    assert summary.dataset_name == "golden_dataset.json"


def test_sync_dataset_to_langsmith_mock():
    """断言 5: [数据飞轮] 同步本地黄金用例集至 LangSmith 云端 Dataset"""
    eval_svc = ServiceProvider.resolve("evaluation_service")

    mock_obs = MagicMock()
    mock_client = MagicMock()
    mock_dataset = MagicMock()
    mock_dataset.id = "mock-dataset-uuid-888"
    mock_dataset.name = "medical-audit-test"

    mock_client.list_datasets.return_value = []
    mock_client.create_dataset.return_value = mock_dataset
    mock_obs._langsmith_client = mock_client
    ServiceProvider.override("observability", mock_obs)

    count = eval_svc.sync_dataset_to_langsmith(
        dataset_name="medical-audit-test",
        file_path="tests/eval/golden_dataset.json"
    )
    assert count == 5
    assert mock_client.create_dataset.called
    assert mock_client.create_example.call_count == 5
