# -*- coding: utf-8 -*-
"""
TDD Suite 3: Entity Schema Grounding & Anti-Patching Defense Tests
===================================================================
Driven by: docs/SPEC_DETERMINISTIC_CACHE_AND_SCHEMA_SEAMS.md
Testing Seam: SceneTableSelector & SQLGuardian Security Boundary

断言目标:
1. 输入自然语言业务术语“调取全市医药机构资质名录库”，系统必须在前置确定性解析阶段将主表绑定为 `fqz_all_yy_yd`，并提供精准物理字段；
2. 安全哨兵 SQLGuardian 必须坚守原则：严禁在安全层内部充当垃圾收集器用补丁把“医药机构资质名录库”替换成物理表，凡是出现不存在的中文表名，直接抛出 SecurityViolationError！
"""
import pytest
from app.core.scene_table_selector import scene_table_selector
from app.skills.security import SQLGuardian, SecurityViolationError


class TestEntitySchemaGrounding:
    """验证业务实体前置锚定与安全哨兵拒绝中文表名"""

    def test_entity_grounding_medical_directory(self):
        """
        [契约测试 5] 前置实体确定性锚定：
        输入业务问题，断言主表确定性解析为 fqz_all_yy_yd，
        且生成的提示词中必须包含物理列名与严禁使用中文表名的硬契约。
        """
        query = "调取全市医药机构资质名录库，统计当前系统内纳管的定点医疗机构与定点零售药店总家数"
        primary, tables = scene_table_selector.select_tables(query)
        assert primary == "fqz_all_yy_yd"
        assert "fqz_all_yy_yd" in tables

        hint = scene_table_selector.get_enforcement_hint(query)
        assert hint is not None
        assert "fqz_all_yy_yd" in hint
        assert "fixmedins_code" in hint
        assert "medins_type" in hint

    def test_sql_guardian_rejects_chinese_hallucinated_table_without_patching(self):
        """
        [红灯测试 6] 拒绝安全层打补丁式字符串替换：
        若上游 Coder 依然写出 `SELECT count(*) FROM 医药机构资质名录库`，
        安全哨兵绝不能在底层悄悄替换为 `fqz_all_yy_yd` 掩耳盗铃，
        而必须严格抛出 SecurityViolationError，迫使上游使用确定性 Schema 映射！
        """
        fake_sql = "SELECT count(*) FROM 医药机构资质名录库 WHERE ddzt = '正常'"
        
        # 严禁在 security.py 里偷偷把 医药机构资质名录库 替换为 fqz_all_yy_yd 并放行执行！
        # 必须抛出 SecurityViolationError 拦截！
        with pytest.raises(SecurityViolationError) as exc_info:
            SQLGuardian.validate_sql(fake_sql)
        
        assert "医药机构资质名录库" in str(exc_info.value) or "幻觉表" in str(exc_info.value)
