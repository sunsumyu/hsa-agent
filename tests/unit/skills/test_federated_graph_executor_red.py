"""
tests/unit/skills/test_federated_graph_executor_red.py
======================================================
Red tests for federated_graph_executor deep module.
Tests:
- execute_fraud_ring_cypher (isolation, success, failure with ontology fallback)
- execute_federated_sideloader (isolation, empty hits, extract failure, ch insert, exception contract)
"""

import pytest
from unittest.mock import MagicMock, patch

from app.skills.federated.federated_graph_executor import (
    execute_fraud_ring_cypher,
    execute_federated_sideloader,
)


class MockNeo4jSession:
    def __init__(self, records=None, raise_exc=None):
        self.records = records or []
        self.raise_exc = raise_exc

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def run(self, cypher):
        if self.raise_exc:
            raise self.raise_exc
        return self.records


class MockNeo4jDriver:
    def __init__(self, session):
        self._session = session

    def session(self):
        return self._session


class MockNeo4jManager:
    def __init__(self, records=None, raise_exc=None, ontology="(:Patient)-[:VISITED]->(:Hospital)"):
        self.session = MockNeo4jSession(records=records, raise_exc=raise_exc)
        self.driver = MockNeo4jDriver(self.session)
        self.ontology = ontology

    def get_driver(self):
        return self.driver

    def get_ontology(self):
        return self.ontology


class MockClickHouseClientInner:
    def __init__(self, fail_create=False, fail_insert=False):
        self.fail_create = fail_create
        self.fail_insert = fail_insert
        self.executed_commands = []
        self.inserted_data = []

    def command(self, cmd):
        if self.fail_create:
            raise RuntimeError("ClickHouse connection dropped on create")
        self.executed_commands.append(cmd)

    def insert(self, table, data, column_names=None):
        if self.fail_insert:
            raise RuntimeError("Disk full on insert")
        self.inserted_data.append((table, data, column_names))


class MockClickHouseClient:
    def __init__(self, fail_create=False, fail_insert=False):
        self.client = MockClickHouseClientInner(fail_create=fail_create, fail_insert=fail_insert)


@pytest.mark.asyncio
async def test_fraud_ring_spatial_isolation_block():
    cypher = "MATCH (n) WHERE n.tab = 'fqz_gz_jzsj_all_ql' RETURN n"
    mgr = MockNeo4jManager()
    res = await execute_fraud_ring_cypher(cypher, neo4j_mgr=mgr)
    assert res["status"] == "ERROR"
    assert "物理拦截" in res["error_message"]
    assert res["sql_logic"] == cypher


@pytest.mark.asyncio
async def test_fraud_ring_success():
    records = [{"p.psn_no": "P001", "cnt": 10}, {"p.psn_no": "P002", "cnt": 12}]
    mgr = MockNeo4jManager(records=records)
    cypher = "MATCH (p:Patient) RETURN p.psn_no, count(*) as cnt"
    res = await execute_fraud_ring_cypher(cypher, neo4j_mgr=mgr)
    assert "report" in res
    assert res["evidence_count"] == 2
    assert len(res["raw_evidence"]) == 2
    assert "[图谱分析]" in res["trace_hint"]


@pytest.mark.asyncio
async def test_fraud_ring_exception_with_ontology_fallback():
    mgr = MockNeo4jManager(raise_exc=RuntimeError("SyntaxError in Cypher"), ontology="Node: Patient")
    cypher = "INVALID CYPHER QUERY"
    res = await execute_fraud_ring_cypher(cypher, neo4j_mgr=mgr)
    assert res["status"] == "ERROR"
    assert "SyntaxError in Cypher" in res["error_message"]
    assert "Node: Patient" in res["suggested_ontology"]
    assert "Neo4j Graph Ontology" in res["suggestion"]


@pytest.mark.asyncio
async def test_sideloader_spatial_isolation_block():
    cypher = "MATCH (n) WHERE n.name = 'fqz_fymx_test' RETURN n"
    mgr = MockNeo4jManager()
    res = await execute_federated_sideloader(cypher, neo4j_mgr=mgr)
    assert res["status"] == "ERROR"
    assert "物理拦截" in res["error_message"]


@pytest.mark.asyncio
async def test_sideloader_empty_records():
    mgr = MockNeo4jManager(records=[])
    cypher = "MATCH (p:Patient {name: 'Nobody'}) RETURN p.id"
    res = await execute_federated_sideloader(cypher, neo4j_mgr=mgr)
    assert res["status"] == "SUCCESS"
    assert res["count"] == 0
    assert "未发现匹配团伙" in res["message"]


@pytest.mark.asyncio
async def test_sideloader_success():
    records = [{"patient_id": "P001"}, {"patient_id": "P002"}]
    mgr = MockNeo4jManager(records=records)
    ch_client = MockClickHouseClient()
    cypher = "MATCH (p:Patient) RETURN p.id as patient_id"

    res = await execute_federated_sideloader(
        cypher=cypher,
        return_key="patient_id",
        neo4j_mgr=mgr,
        clickhouse_client_getter=lambda: ch_client
    )
    assert res["status"] == "SIDELOADED"
    assert "fqz_temp_sl_" in res["temp_table"]
    assert "INNER JOIN" in res["instruction"]
    assert len(ch_client.client.inserted_data) == 1
    assert ch_client.client.inserted_data[0][1] == [["P001"], ["P002"]]


@pytest.mark.asyncio
async def test_sideloader_ch_error_contract():
    records = [{"patient_id": "P001"}]
    mgr = MockNeo4jManager(records=records)
    ch_client = MockClickHouseClient(fail_insert=True)
    cypher = "MATCH (p:Patient) RETURN p.id as patient_id"

    res = await execute_federated_sideloader(
        cypher=cypher,
        return_key="patient_id",
        neo4j_mgr=mgr,
        clickhouse_client_getter=lambda: ch_client
    )
    assert res is not None
    assert res["status"] == "ERROR"
    assert "侧载到 ClickHouse 失败" in res["error_message"]
