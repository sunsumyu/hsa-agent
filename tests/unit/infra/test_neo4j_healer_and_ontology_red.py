"""
tests/unit/infra/test_neo4j_healer_and_ontology_red.py
=====================================================
[Matt Pocock Deep Module Red Test] Neo4j 协议自愈探活与本体模板解耦架构审计
"""

import pytest
from app.infra.neo4j_protocol_healer import Neo4jProtocolHealer
from app.infra.neo4j_ontology_provider import Neo4jOntologyProvider
from app.infra.neo4j_manager import Neo4jManager


def test_neo4j_protocol_healer_heal_uri():
    """验证本地环境协议自愈 (neo4j:// -> bolt://) 与远程保留"""
    healer = Neo4jProtocolHealer()

    # 本地协议应自愈为 bolt://
    assert healer.heal_uri("neo4j://localhost:7687") == "bolt://localhost:7687"
    assert healer.heal_uri("neo4j://127.0.0.1:7687") == "bolt://127.0.0.1:7687"

    # 远程集群应保持原样
    assert healer.heal_uri("neo4j://remote-graph.internal:7687") == "neo4j://remote-graph.internal:7687"
    assert healer.heal_uri("bolt://localhost:7687") == "bolt://localhost:7687"


def test_neo4j_protocol_healer_probe_port(monkeypatch):
    """验证 socket 端口探测与异常优雅降级"""
    healer = Neo4jProtocolHealer()

    # 测试解析 host/port
    host, port = healer.parse_endpoint("bolt://localhost:7687")
    assert host == "localhost"
    assert port == 7687

    host_default, port_default = healer.parse_endpoint("bolt://127.0.0.1")
    assert host_default == "127.0.0.1"
    assert port_default == 7687

    # 探测不可达端口（如使用一个未监听的端口），应返回 False 而非崩溃
    reachable, h, p = healer.probe_port("bolt://127.0.0.1:59999", timeout=0.1)
    assert reachable is False
    assert h == "127.0.0.1"
    assert p == 59999


def test_neo4j_ontology_provider_format():
    """验证本体模板生成器与 Cypher 规范注入"""
    provider = Neo4jOntologyProvider()

    hints = provider.get_audit_graph_hints()
    assert "HSA 医保审计图谱模式" in hints
    assert "(p:Patient {psn_no})" in hints
    assert "VISITED" in hints
    assert "HAS_PHONE" in hints

    # 格式化本体
    ontology = provider.format_ontology(
        labels=["Patient", "Hospital", "Phone"],
        rel_types=["VISITED", "HAS_PHONE"]
    )
    assert "**[Neo4j Graph Ontology]**" in ontology
    assert "- **Labels**: Patient, Hospital, Phone" in ontology
    assert "- **Relationships**: VISITED, HAS_PHONE" in ontology
    assert hints in ontology


def test_neo4j_manager_fallback_when_offline():
    """验证当物理连接未就绪时，Neo4jManager 能优雅返回权威本体，不抛异常"""
    mgr = Neo4jManager()
    mgr.is_connected = False
    mgr.driver = None

    onto = mgr.get_ontology()
    assert "HSA 医保审计图谱模式" in onto
    assert "(p:Patient {psn_no})" in onto
