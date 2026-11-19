import pytest
from unittest.mock import AsyncMock, patch
from app.skills.rule_catalog import rule_catalog, RuleCatalog
from app.skills.rule_execution import RuleExecutionSkill


def test_rule_catalog_resolution():
    catalog = RuleCatalog()
    assert catalog.resolve_target_id("核查性别不符") == "GENDER_CONFLICT"
    assert catalog.resolve_target_id("gender_check") == "GENDER_CONFLICT"
    assert catalog.resolve_target_id("高频购药排查") == "HIGH_FREQ_DRUG_PURCHASE"
    assert catalog.resolve_target_id("分解住院排查") == "DECOMPOSITION_HOSPITALIZATION"
    assert catalog.resolve_target_id("跨机构重复住院") == "CROSS_HOSPITAL_OVERLAP"
    assert catalog.resolve_target_id("重复收费核查") == "REPEAT_BILLING_DETECTOR"
    assert catalog.resolve_target_id("共用联系方式") == "CONTACT_SHARING"
    assert catalog.resolve_target_id("VIX变异扫描") == "DYNAMIC_VIX_SCAN"
    assert catalog.resolve_target_id("离群值分析") == "STATISTICAL_OUTLIER_DETECTOR"
    assert catalog.resolve_target_id("聚集就医挖掘") == "FEDERATED_CLUSTER_CYPHER"
    assert catalog.resolve_target_id("稳健MAD检测") == "ROBUST_MAD_DETECTOR"
    assert catalog.resolve_target_id("custom_unknown_rule") == "CUSTOM_UNKNOWN_RULE"


def test_rule_catalog_methodology_and_tolerance():
    catalog = RuleCatalog()
    methodology = catalog.get_methodology("GENDER_CONFLICT")
    assert "性别冲突校验" in methodology
    assert "医疗保障基金使用监督管理条例" in methodology

    unknown_meth = catalog.get_methodology("CUSTOM_RULE")
    assert unknown_meth == "自定义规则逻辑匹配"

    assert catalog.get_tolerance("GENDER_CONFLICT") == 50000
    assert catalog.get_tolerance("REPEAT_BILLING_DETECTOR") == 50000
    assert catalog.get_tolerance("HIGH_FREQ_DRUG_PURCHASE") == 1000


@pytest.mark.asyncio
async def test_rule_execution_skill_delegates_to_catalog():
    skill = RuleExecutionSkill()
    fake_sql = "SELECT * FROM fqz_fymx_test WHERE gend = '1' LIMIT 10"
    fake_raw_data = [{"psn_no": "P01", "medfee": 120.0}]

    with patch("app.skills.audit_rules.AuditRuleEngine.get_rule_sql", return_value=fake_sql):
        with patch("app.skills.rule_execution._execute_audit_sql_logic", new_callable=AsyncMock, return_value=fake_raw_data) as mock_exec:
            res = await skill._arun("性别冲突核查")

            assert "report" in res
            assert res["evidence_count"] == 1
            assert res["sql_logic"] == fake_sql
            assert "性别冲突校验" in res["methodology"]
            assert "【规则对撞】" in res["report"]
            mock_exec.assert_awaited_once_with(fake_sql, return_raw=True, tolerance=50000)
