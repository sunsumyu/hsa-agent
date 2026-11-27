"""
tests/unit/memory/test_entity_extractor_deep_red.py
===================================================
Matt Pocock Deep Module 风格的单元测试：
针对 EvidenceKnowledgeGraphManager 与 entity_extractor 深模块化：
1. 实体与边关系抽取（机构、患者、违规政策、金额、记录单号）
2. 空/无实体场景的稽核中心兜底聚合
3. 多会话状态隔离（支持多 session 并发写入与独立查询）
4. 不存在会话的安全降级（友好提示消息结构）
5. 会话冲突检测一站式委托（detect_session_conflicts）
6. spaCy 模型缺失/异常下的平滑自愈降级
7. 模块级旧 API 兼容性（extract_graph, update_latest_findings, get_latest_graph）
"""

import pytest
from app.core.memory.entity_extractor import (
    EvidenceKnowledgeGraphManager,
    evidence_graph_manager,
    extract_graph,
    update_latest_findings,
    get_latest_graph,
    CATEGORIES,
)


@pytest.fixture(autouse=True)
def clean_manager():
    """每次测试前清空单例状态"""
    evidence_graph_manager.clear()
    yield
    evidence_graph_manager.clear()


def test_extract_graph_full_entities():
    findings = [
        "发现第一人民医院存在超量开药违规行为，患者：P_001928，涉及涉案金额：15800.50元，结算记录#SETL-889921。",
    ]
    graph = extract_graph(findings)

    assert "nodes" in graph
    assert "edges" in graph
    assert "categories" in graph
    assert graph["total"] == len(graph["nodes"])

    node_names = [n["name"] for n in graph["nodes"]]
    # 医院
    assert any("第一人民医院" in name for name in node_names)
    # 患者
    assert any("P_001928" in name for name in node_names)
    # 政策
    assert any("超量开药" in name for name in node_names)
    # 金额
    assert any("15,800" in name or "15,801" in name or "15800" in name for name in node_names)
    # 记录
    assert any("SETL-889921" in name for name in node_names)

    # 边关系验证
    edge_labels = [e["label"] for e in graph["edges"]]
    assert "涉及" in edge_labels
    assert "关联" in edge_labels
    assert "就诊于" in edge_labels
    assert "违反" in edge_labels
    assert "金额" in edge_labels
    assert "依据" in edge_labels


def test_extract_graph_fallback_center_node():
    findings = [
        "经专项核查，当前流水批次各项指标正常，未触发任何疑点规则与报警阈值。",
    ]
    graph = extract_graph(findings)

    node_names = [n["name"] for n in graph["nodes"]]
    assert "稽核中心" in node_names
    # 包含 edge 关系
    labels = [e["label"] for e in graph["edges"]]
    assert "包含" in labels


def test_multi_session_isolation():
    manager = EvidenceKnowledgeGraphManager()

    findings_session_a = ["某某市第三人民医院超量开药涉案金额：5000元"]
    findings_session_b = ["某某市妇幼保健院分解住院涉案金额：80000元"]

    manager.record_session_findings("session_A", findings_session_a)
    manager.record_session_findings("session_B", findings_session_b)

    # 查 session_A
    graph_a = manager.get_session_graph("session_A")
    names_a = [n["name"] for n in graph_a["nodes"]]
    assert any("第三人民医院" in n for n in names_a)
    assert not any("妇幼保健院" in n for n in names_a)

    # 查 session_B
    graph_b = manager.get_session_graph("session_B")
    names_b = [n["name"] for n in graph_b["nodes"]]
    assert any("妇幼保健院" in n for n in names_b)
    assert not any("第三人民医院" in n for n in names_b)

    # 查最新（最后写入的 session_B）
    graph_latest = manager.get_session_graph()
    names_latest = [n["name"] for n in graph_latest["nodes"]]
    assert any("妇幼保健院" in n for n in names_latest)


def test_nonexistent_session_graceful_response():
    manager = EvidenceKnowledgeGraphManager()
    res = manager.get_session_graph("nonexistent_session_999")
    assert res["nodes"] == []
    assert res["edges"] == []
    assert res["total"] == 0
    assert "nonexistent_session_999" in res["message"]


def test_detect_session_conflicts_delegation():
    manager = EvidenceKnowledgeGraphManager()
    conflicting_findings = [
        "经核查，康复医院涉案金额为 10000.00 元。",
        "经核查，康复医院涉案金额为 99000.00 元。",
    ]
    manager.record_session_findings("conflict_session", conflicting_findings)

    conflicts = manager.detect_session_conflicts("conflict_session")
    assert len(conflicts) >= 1
    assert conflicts[0]["type"] == "AMOUNT_MISMATCH"
    assert "康复医院" in conflicts[0]["entity"]


def test_spacy_fallback_graceful(monkeypatch):
    from app.core.memory import entity_extractor

    # 模拟 spacy 导入失败
    monkeypatch.setattr(entity_extractor, "_NLP", None)
    
    import builtins
    real_import = builtins.__import__
    def mock_import(name, *args, **kwargs):
        if name == "spacy":
            raise ImportError("spacy disabled for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    manager = EvidenceKnowledgeGraphManager()
    res = manager.extract_graph(["第一人民医院涉案金额100元"])
    assert res["total"] >= 2
    assert manager.get_nlp() is False


def test_backward_compatibility_module_api():
    # 测试通过旧的全局函数访问
    update_latest_findings("legacy_session", ["仁爱医院超量开药涉案金额：1200元"])
    
    latest_graph = get_latest_graph()
    names = [n["name"] for n in latest_graph["nodes"]]
    assert any("仁爱医院" in n for n in names)

    # 访问指定 session
    legacy_graph = get_latest_graph("legacy_session")
    assert legacy_graph["total"] > 0
