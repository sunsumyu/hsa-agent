"""
Red tests for schema_domain_router deep module.
Follows Red -> Green -> Refactor cycle.
"""
import pytest


def test_schema_domain_router_import_and_defaults():
    from app.skills.schema_domain_router import (
        classify_question_domains,
        semantic_classify_domains,
        resolve_target_tables,
        get_ontology_hints,
        DATA_DOMAINS,
        DEFAULT_TABLES,
    )
    assert len(DATA_DOMAINS) >= 4
    assert DEFAULT_TABLES == ["FQZ_GZ_JZSJ_ALL_QL"]

    # 空问题兜底测试
    empty_domains = classify_question_domains("")
    assert empty_domains[0]["domain"] == "settlement"

    empty_semantic = semantic_classify_domains("   ")
    assert empty_semantic[0]["domain"] == "settlement"

    empty_tables = resolve_target_tables("")
    assert empty_tables == ["FQZ_GZ_JZSJ_ALL_QL"]


def test_schema_domain_routing_keywords():
    from app.skills.schema_domain_router import (
        classify_question_domains,
        resolve_target_tables,
    )
    # 药品目录
    drug_domains = classify_question_domains("请查询该药品的医保目录编码与处方用药规范")
    assert drug_domains[0]["domain"] == "drug_catalog"
    drug_tables = resolve_target_tables("请查询该药品的医保目录编码与处方用药规范")
    assert "FQZ_DRUG_MCS_INFO_LIST" in drug_tables

    # 门诊明细
    fymx_domains = classify_question_domains("核查乡镇卫生院门诊统筹批量刷单明细")
    assert fymx_domains[0]["domain"] == "outpatient_detail"
    fymx_tables = resolve_target_tables("核查乡镇卫生院门诊统筹批量刷单明细")
    assert "FQZ_FYMX_TEST" in fymx_tables

    # 医院月度
    hosp_domains = classify_question_domains("统计各医疗机构月度汇总费用与VIX变异指数")
    assert hosp_domains[0]["domain"] == "hospital_monthly"
    hosp_tables = resolve_target_tables("统计各医疗机构月度汇总费用与VIX变异指数")
    assert "FQZ_ALL_YY_YD_1" in hosp_tables


def test_schema_domain_ontology_hints():
    from app.skills.schema_domain_router import (
        get_ontology_hints,
        semantic_classify_domains,
    )
    hints = get_ontology_hints("核查患者是否存在空间距离异常或跨市就医")
    assert hints is not None
    assert "admdvs" in hints
    assert "跨市" in hints

    # 跨域本体在语义分类中会提高对应域权重
    semantic_res = semantic_classify_domains("空间跨市时序碰撞")
    domains_hit = [d["domain"] for d in semantic_res]
    assert "settlement" in domains_hit
    assert "hospital_monthly" in domains_hit


def test_schema_injector_delegation_facade():
    from app.skills.schema_injector import schema_injector
    # 验证门面委托一致性
    c_res = schema_injector.classify("药品处方目录")
    assert c_res[0]["domain"] == "drug_catalog"

    t_res = schema_injector.get_target_tables("乡镇卫生院门诊刷单")
    assert "FQZ_FYMX_TEST" in t_res

    hint = schema_injector.get_ontology_hint("空间跨市")
    assert hint and "admdvs" in hint

    # 验证 inject 依然正常运行
    inject_str = schema_injector.inject("门诊统筹刷单", top_k=5)
    assert "FQZ_FYMX_TEST" in inject_str
    assert "审计治理与安全禁区" in inject_str

