from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.reporting.llm_judge import AuditJudge, audit_judge


def test_sanitize_for_prompt_masks_pii_strips_sql_and_truncates():
    raw = (
        '"psn_no=P123" "phone=13800001111" "id_card=4401011990"\n'
        "sql: ```sql\nSELECT * FROM secret_table\n```\x07"
    )
    sanitized = AuditJudge._sanitize_for_prompt(raw + ("A" * 2500), max_length=300)
    assert "P123" not in sanitized
    assert "13800001111" not in sanitized
    assert "4401011990" not in sanitized
    assert '"***"' in sanitized
    assert "SELECT * FROM secret_table" not in sanitized
    assert "[SQL 查询已隐藏]" in sanitized
    assert "\x07" not in sanitized
    assert len(sanitized) <= 300


@pytest.mark.asyncio
async def test_evaluate_finding_valid_high_confidence():
    mock_resp = SimpleNamespace(
        content='```json\n{"is_valid": true, "confidence_score": 88, "refutation_reason": "", "action": "PASS"}\n```'
    )
    with patch("app.core.llm_provider.llm_provider.chat", new_callable=AsyncMock, return_value=mock_resp):
        result = await audit_judge.evaluate_finding({"violation_type": "分解住院"}, '[{"cnt": 3}]')

    assert result["is_valid"] is True
    assert result["confidence_score"] == 88
    assert result["action"] == "PASS"


@pytest.mark.asyncio
async def test_evaluate_finding_low_confidence_downgrades_to_re_audit():
    mock_resp = SimpleNamespace(
        content='{"is_valid": true, "confidence_score": 55, "refutation_reason": "", "action": "PASS"}'
    )
    with patch("app.core.llm_provider.llm_provider.chat", new_callable=AsyncMock, return_value=mock_resp):
        result = await AuditJudge.evaluate_finding({"violation_type": "超量开药"}, '[{"cnt": 2}]')

    assert result["is_valid"] is False
    assert result["action"] == "RE_AUDIT"
    assert "70" in result["refutation_reason"]


@pytest.mark.asyncio
async def test_evaluate_finding_malformed_json_returns_safe_fallback():
    mock_resp = SimpleNamespace(content="not valid json response")
    with patch("app.core.llm_provider.llm_provider.chat", new_callable=AsyncMock, return_value=mock_resp):
        result = await AuditJudge.evaluate_finding({"violation_type": "虚构医药服务"}, "[]")

    assert result["is_valid"] is False
    assert result["confidence_score"] == 10
    assert result["action"] == "RE_AUDIT"
    assert "parsing error" in result["refutation_reason"]
