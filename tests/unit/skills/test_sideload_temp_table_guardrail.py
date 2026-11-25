# tests/unit/skills/test_sideload_temp_table_guardrail.py
import pytest
import yaml
from pathlib import Path
from app.skills.security import SQLGuardian, SecurityViolationError


def test_sql_guardian_allows_federated_sideload_temp_table_join():
    sql = (
        "SELECT a.psn_no, SUM(a.medfee_sumamt) AS total_fee "
        "FROM fqz_gz_jzsj_all_ql AS a "
        "INNER JOIN fqz_temp_sl_a1b2c3d4 AS b ON a.psn_no = b.id "
        "GROUP BY a.psn_no"
    )
    validated = SQLGuardian.validate_sql(sql, expected_table="fqz_gz_jzsj_all_ql")
    assert "fqz_temp_sl_a1b2c3d4" in validated
    assert "b.id" in validated or ".id" in validated


def test_sql_guardian_still_blocks_unknown_column_on_sideload_join():
    bad_sql = (
        "SELECT a.psn_no, b.non_existent_secret_col "
        "FROM fqz_gz_jzsj_all_ql AS a "
        "INNER JOIN fqz_temp_sl_a1b2c3d4 AS b ON a.psn_no = b.id"
    )
    with pytest.raises(SecurityViolationError):
        SQLGuardian.validate_sql(bad_sql, expected_table="fqz_gz_jzsj_all_ql")


def test_docker_compose_declares_neo4j_service():
    compose_path = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    doc = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    assert "neo4j" in doc["services"]
    ports = " ".join(str(p) for p in doc["services"]["neo4j"].get("ports", []))
    assert "7687" in ports
