import pytest
from unittest.mock import MagicMock
from app.infra.complexity_classifier import ComplexityClassifier
from app.infra.local_service_detector import LocalServiceDetector
from app.infra.model_pool_router import ModelPoolRouter
from app.infra.model_manager import ModelManager


def test_complexity_classifier_logic():
    """测试启发式复杂度分类深模块"""
    classifier = ComplexityClassifier()
    assert classifier.classify("排查跨机构欺诈团伙路径") == "HIGH"
    assert classifier.classify("显示重复收费总数") == "LOW"
    assert classifier.classify("评估就医合理性") == "MEDIUM"
    assert classifier.classify("") == "MEDIUM"


def test_local_service_detector_discovery():
    """测试本地服务探测深模块接口"""
    detector = LocalServiceDetector()
    providers = {}
    # 测试在无可用本地端口时不崩溃并返回安全字典
    discovered = detector.discover_local_services(existing_providers=providers)
    assert isinstance(discovered, dict)


def test_model_pool_router_pool_selection():
    """测试算力池路由器深模块"""
    mock_pool_mgr = MagicMock()
    mock_tracker = MagicMock()
    mock_factory = MagicMock()

    router = ModelPoolRouter(
        pool_manager=mock_pool_mgr,
        usage_tracker=mock_tracker,
        llm_factory=mock_factory,
    )

    # 验证接口方法存在
    assert hasattr(router, "get_llm_from_pool")
    assert hasattr(router, "get_adaptive_llm")
    assert hasattr(router, "get_llm_by_role")


def test_model_manager_facade_delegation():
    """测试 ModelManager 门面协同委托各深模块"""
    mm = ModelManager()
    assert mm.classify_complexity_locally("排查欺诈环") == "HIGH"
    assert hasattr(mm, "get_model_list")
    assert hasattr(mm, "get_adaptive_llm")
    assert hasattr(mm, "get_llm_by_role")
