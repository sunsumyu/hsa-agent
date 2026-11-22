"""
tests/unit/skills/test_federated_sideload_buffer_deep_red.py
===========================================================
[Matt Pocock Deep Module Red Test] 联邦跨库侧载缓冲生命周期解耦架构审计
"""

from unittest.mock import MagicMock
import pytest
from app.skills.federated.federated_sideload_buffer import FederatedSideloadBuffer
from app.skills.federated.federated_graph_executor import execute_federated_sideloader


def test_federated_sideload_buffer_legacy_driver_execute():
    """验证使用经典 clickhouse-driver (execute 方法) 的建表与批量插入"""
    buffer = FederatedSideloadBuffer()

    mock_client = MagicMock()
    mock_client.client.execute = MagicMock()
    del mock_client.client.command  # 确保走 execute 分支

    ok, table_name, err = buffer.sideload_ids_to_clickhouse(
        ids=["ID001", "ID002"],
        client=mock_client
    )

    assert ok is True
    assert err is None
    assert table_name.startswith("fqz_temp_sl_")
    assert mock_client.client.execute.call_count == 2  # 一次 CREATE，一次 INSERT


def test_federated_sideload_buffer_modern_driver_command_insert():
    """验证使用现代 clickhouse-connect (command + insert) 的建表与插入"""
    buffer = FederatedSideloadBuffer()

    mock_client = MagicMock()
    # 模拟没有 execute，只有 command 和 insert
    del mock_client.client.execute
    mock_client.client.command = MagicMock()
    mock_client.client.insert = MagicMock()

    ok, table_name, err = buffer.sideload_ids_to_clickhouse(
        ids=["ID003"],
        client=mock_client
    )

    assert ok is True
    assert err is None
    assert table_name.startswith("fqz_temp_sl_")
    mock_client.client.command.assert_called_once()
    mock_client.client.insert.assert_called_once()


def test_federated_sideload_buffer_error_handling():
    """验证 ClickHouse 物理写入异常时的弹性捕获与状态返回"""
    buffer = FederatedSideloadBuffer()

    mock_client = MagicMock()
    mock_client.client.execute.side_effect = RuntimeError("ClickHouse out of memory")

    ok, table_name, err = buffer.sideload_ids_to_clickhouse(
        ids=["ID_ERR"],
        client=mock_client
    )

    assert ok is False
    assert "ClickHouse out of memory" in err


@pytest.mark.asyncio
async def test_execute_federated_sideloader_end_to_end():
    """验证 execute_federated_sideloader 协同执行流水线"""
    fake_records = [{"p": {"psn_no": "P101"}}, {"p": {"psn_no": "P102"}}]

    mock_neo4j = MagicMock()
    mock_session = MagicMock()
    mock_session.run.return_value = fake_records
    mock_neo4j.get_driver.return_value.session.return_value.__enter__.return_value = mock_session

    mock_ch = MagicMock()
    mock_ch.client.execute = MagicMock()

    result = await execute_federated_sideloader(
        cypher="MATCH (p:Patient)-[:HAS_PHONE]->(t:Phone) RETURN p",
        return_key="psn_no",
        neo4j_mgr=mock_neo4j,
        clickhouse_client_getter=lambda: mock_ch
    )

    assert result["status"] == "SIDELOADED"
    assert "在 Neo4j 中发现了 2 个目标实体" in result["message"]
    assert "temp_table" in result
    assert result["temp_table"].startswith("fqz_temp_sl_")
