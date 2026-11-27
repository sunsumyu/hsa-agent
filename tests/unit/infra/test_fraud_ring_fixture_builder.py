# tests/unit/infra/test_fraud_ring_fixture_builder.py
from unittest.mock import MagicMock
from app.infra.fraud_ring_fixture_builder import (
    build_golden_fraud_ring_rows,
    seed_fraud_rings_to_clickhouse,
    sync_fraud_rings_to_neo4j,
)


def test_golden_fraud_ring_rows_exact_ground_truth():
    rows = build_golden_fraud_ring_rows()
    assert len(rows) == 6
    phones = {r["tel"] for r in rows}
    assert phones == {"13800009901", "13800009902"}
    total_fee = round(sum(r["medfee_sumamt"] for r in rows), 2)
    assert total_fee == 3600.00


def test_seed_and_sync_fraud_rings_handles_offline_neo4j_gracefully():
    mock_ck = MagicMock()
    inserted = seed_fraud_rings_to_clickhouse(mock_ck)
    assert inserted == 6
    assert mock_ck.query.call_count == 2  # cleanup DELETE + INSERT

    offline_neo4j = MagicMock()
    offline_neo4j.execute_cypher.side_effect = RuntimeError("Neo4j offline")
    synced = sync_fraud_rings_to_neo4j(offline_neo4j, build_golden_fraud_ring_rows())
    assert synced is False


def test_sync_fraud_rings_to_neo4j_succeeds_when_online():
    online_neo4j = MagicMock()
    rows = build_golden_fraud_ring_rows()
    synced = sync_fraud_rings_to_neo4j(online_neo4j, rows)
    assert synced is True
    online_neo4j.execute_cypher.assert_called_once()
    cypher_arg, params_arg = online_neo4j.execute_cypher.call_args[0]
    assert "HAS_PHONE" in cypher_arg
    assert params_arg == {"rows": rows}


def test_seed_fixtures_wires_dual_store_fraud_ring_seeding():
    from unittest.mock import patch
    import scripts.seed_golden_benchmark_fixtures as seed_mod

    mock_ck = MagicMock()
    mock_neo4j = MagicMock()
    with (
        patch.object(seed_mod, "get_clickhouse_client", return_value=mock_ck),
        patch("app.infra.neo4j_manager.neo4j_manager", mock_neo4j),
    ):
        seed_mod.seed_fixtures()

    executed_sqls = [call.args[0] for call in mock_ck.query.call_args_list]
    assert any("GOLDEN_RING_%" in sql for sql in executed_sqls)
    assert any("GOLDEN_RING_A1" in sql and "13800009901" in sql for sql in executed_sqls)
    mock_neo4j.execute_cypher.assert_called_once()

