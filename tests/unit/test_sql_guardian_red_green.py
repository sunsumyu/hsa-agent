"""
tests/unit/test_sql_guardian_red_green.py
=========================================
SQLGuardian / AST 神经符号门禁红绿灯测试套件 (TDD 模式)
针对场景：伴随依赖缺失型审计（如无手术收麻醉费）
"""

import pytest
import sqlglot
from app.core.guardrails.contradiction_detector import ContradictionDetector, ContradictionViolation
from app.core.registry.archetype_registry import AuditArchetype, ArchetypeCategory


@pytest.fixture
def missing_companion_archetype():
    """定义伴随依赖缺失领域原型"""
    return AuditArchetype(
        category=ArchetypeCategory.MISSING_COMPANION,
        name="missing_companion",
        display_name="伴随依赖缺失",
        keywords=()
    )


# ==============================================================================
# 🔴 红灯测试区 (Red Tests): 必须精准拦截并报错的反模式坏 SQL
# ==============================================================================

class TestRedCasesAntiPatterns:
    """红灯测试：验证大模型生成的典型反模式 SQL 必须被 100% 静态拦截"""

    def test_red_single_row_pseudo_exclusion_like(self, missing_companion_archetype):
        """
        🔴 红灯 Case 1: 单行伪排除反模式 (Single-Row Pseudo-Exclusion)
        特征：在明细大宽表的 WHERE 子句中，同行同时使用 LIKE 包含与 NOT LIKE 排除。
        危害：因为单行只代表单一流水，麻醉行绝不可能包含'手术'，导致全量误报 (100% 假阳性)。
        """
        bad_sql = """
        SELECT setl_id, psn_name, hilist_name, det_item_fee_sumamt 
        FROM fqz_fymx_test 
        WHERE hilist_name LIKE '%麻醉%' 
          AND hilist_name NOT LIKE '%手术%'
        """
        
        # 断言：必须触发拦截，返回 Violation 对象
        violation = ContradictionDetector.detect(bad_sql, archetypes=[missing_companion_archetype])
        assert violation is not None, "🔴 致命漏洞：未拦截单行伪排除反模式！"
        assert violation.column.lower() == "hilist_name"
        assert "伴随依赖缺失" in violation.message or "单行伪排除" in violation.message or "分解收费" in violation.message
        assert len(violation.conflicting_predicates) >= 2

    def test_red_scalar_contradiction_inverted_range(self):
        """
        🔴 红灯 Case 2: 数值上下界区间倒置矛盾 (Inverted Range)
        特征：下限大于上限，导致解集在代数上恒为空集。
        """
        bad_sql = """
        SELECT setl_id, det_item_fee_sumamt 
        FROM fqz_fymx_test 
        WHERE det_item_fee_sumamt > 1000 AND det_item_fee_sumamt < 100
        """
        
        violation = ContradictionDetector.detect(bad_sql)
        assert violation is not None, "🔴 致命漏洞：未拦截上下界倒置矛盾！"
        assert violation.column.lower() == "det_item_fee_sumamt"
        assert "区间" in violation.message or "矛盾" in violation.message

    def test_red_binary_enum_exhaustive_exclusion(self):
        """
        🔴 红灯 Case 3: 二元枚举全排除矛盾 (Binary Enum Exhaustive Exclusion)
        特征：对二元性别字段 gend 同时做 NOT LIKE '1%' AND NOT LIKE '2%'。
        """
        bad_sql = """
        SELECT setl_id FROM fqz_fymx_test 
        WHERE hilist_name LIKE '%宫内节育%' 
          AND gend NOT LIKE '1%' 
          AND gend NOT LIKE '2%'
        """
        
        violation = ContradictionDetector.detect(bad_sql)
        assert violation is not None, "🔴 致命漏洞：未拦截二元枚举全排除矛盾！"
        assert violation.column.lower() == "gend"


# ==============================================================================
# 🟢 绿灯测试区 (Green Tests): 合法、跨行关联、复杂的 SQL 必须全部放行
# ==============================================================================

class TestGreenCasesLegitimateQueries:
    """绿灯测试：验证复杂正确的查询绝不被误杀"""

    def test_green_subquery_cross_row_verification(self, missing_companion_archetype):
        """
        🟢 绿灯 Case 1: 子查询跨行对撞 (NOT IN Subquery)
        合规逻辑：在单据/结算维度 (setl_id) 判断该就诊是否包含手术记录。
        """
        good_sql = """
        SELECT setl_id, psn_name, hilist_name 
        FROM fqz_fymx_test 
        WHERE hilist_name LIKE '%麻醉%' 
          AND setl_id NOT IN (
              SELECT setl_id FROM fqz_fymx_test WHERE hilist_name LIKE '%手术%'
          )
        """
        
        # 断言：必须放行，返回 None
        violation = ContradictionDetector.detect(good_sql, archetypes=[missing_companion_archetype])
        assert violation is None, f"🟢 误杀正常查询: {violation.message if violation else ''}"

    def test_green_cte_cross_row_verification(self, missing_companion_archetype):
        """
        🟢 绿灯 Case 2: CTE 公用表表达式跨行关联 (WITH clause)
        合规逻辑：通过 CTE 预先提炼手术清单，主查询做 LEFT JOIN 并校验手术记录为 NULL。
        """
        good_cte_sql = """
        WITH surgery_records AS (
            SELECT DISTINCT setl_id 
            FROM fqz_fymx_test 
            WHERE hilist_name LIKE '%手术%'
        )
        SELECT a.setl_id, a.psn_name, a.det_item_fee_sumamt 
        FROM fqz_fymx_test a
        LEFT JOIN surgery_records b ON a.setl_id = b.setl_id
        WHERE a.hilist_name LIKE '%麻醉%' 
          AND b.setl_id IS NULL
        """
        
        violation = ContradictionDetector.detect(good_cte_sql, archetypes=[missing_companion_archetype])
        assert violation is None, "🟢 误杀合法 CTE 跨行关联查询！"

    def test_green_disjunction_or_legitimate(self):
        """
        🟢 绿灯 Case 3: 析取 OR 逻辑放行
        合规逻辑：同一字段在 OR 关系下的不同取值是合法的析取，不属于互斥矛盾。
        """
        good_or_sql = """
        SELECT setl_id FROM fqz_fymx_test 
        WHERE (gend = '1' OR gend = '2') 
          AND det_item_fee_sumamt > 50
        """
        
        violation = ContradictionDetector.detect(good_or_sql)
        assert violation is None, "🟢 误杀合法的 OR 析取条件！"


# ==============================================================================
# 🟡 边界与健壮性测试区 (Edge Cases)
# ==============================================================================

class TestEdgeCasesRobustness:
    """边界测试：抗混淆与深层嵌套 AST 遍历能力"""

    def test_edge_nested_parentheses_and_aliases(self, missing_companion_archetype):
        """
        🟡 边界 Case 1: 复杂嵌套括号与表别名穿透
        验证即使用户加了多层冗余括号与表别名，门禁依然能准确嗅探到单行伪排除。
        """
        obfuscated_bad_sql = """
        SELECT t.setl_id FROM fqz_fymx_test AS t
        WHERE ((t.hilist_name LIKE '%麻醉%') AND ((t.det_item_fee_sumamt > 0) AND (t.hilist_name NOT LIKE '%手术%')))
        """
        
        violation = ContradictionDetector.detect(obfuscated_bad_sql, archetypes=[missing_companion_archetype])
        assert violation is not None, "🟡 边界失效：冗余括号导致门禁漏检！"

    def test_unprotected_vs_protected_audit_query_comparison(self, missing_companion_archetype):
        """
        🔥 实战对比验证：
        1. 【无防护状态】：大模型写的坏 SQL 直接下发数据库，看查出了什么（假阳性雪崩，正常人被冤枉）；
        2. 【有防护状态】：经 AST 神经符号门禁拦截并自愈修正为跨行对撞后，看查出了什么（零误报，只抓真骗保）。
        """
        import sqlite3

        # 1. 搭建仿真内存数据库，注入真实医保结算流水
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE fqz_fymx_test (
            setl_id TEXT,
            psn_name TEXT,
            hilist_name TEXT,
            det_item_fee_sumamt REAL
        )
        """)

        # 插入测试流水样本：
        # 患者 A (张三，setl_001)：明明做了阑尾切除手术，正常收麻醉费（合规守法病人）
        cursor.execute("INSERT INTO fqz_fymx_test VALUES ('setl_001', '张三', '全身麻醉费', 800.0)")
        cursor.execute("INSERT INTO fqz_fymx_test VALUES ('setl_001', '张三', '腹腔镜阑尾切除手术', 3500.0)")

        # 患者 B (李四，setl_002)：没有任何手术，却莫名收了麻醉费（真实违规骗保嫌疑单据）
        cursor.execute("INSERT INTO fqz_fymx_test VALUES ('setl_002', '李四', '局部浸润麻醉费', 300.0)")
        conn.commit()

        # ==============================================================================
        # ❌ 实验 1：【无防护模式】(未挂门禁，直接把大模型生成的单行排除 SQL 丢给数据库)
        # ==============================================================================
        unprotected_bad_sql = """
        SELECT setl_id, psn_name, hilist_name, det_item_fee_sumamt 
        FROM fqz_fymx_test AS t
        WHERE ((t.hilist_name LIKE '%麻醉%') AND ((t.det_item_fee_sumamt > 0) AND (t.hilist_name NOT LIKE '%手术%')))
        """

        cursor.execute(unprotected_bad_sql)
        unprotected_results = cursor.fetchall()

        print("\n" + "="*70)
        print("[TEST-RESULT] [UNPROTECTED-MODE] Query Results (Directly executing LLM SQL):")
        for row in unprotected_results:
            print(f"   -> [VIOLATION-FLAGGED] setl_id: {row[0]} | patient: {row[1]} | item: {row[2]} | fee: {row[3]}")
        
        # 结果分析：
        # 张三明明做了切除手术，却因为'全身麻醉费'这一行不含'手术'二字，被直接定性为违规！
        accused_names_unprotected = [row[1] for row in unprotected_results]
        assert "张三" in accused_names_unprotected, "无防护状态下，正常病人张三理应被错误冤枉！"
        assert "李四" in accused_names_unprotected
        print(f"   [WARN] Disaster: Patient Zhang San had legitimate surgery, but was WRONGLY FLAGGED as fraud!")

        # ==============================================================================
        # 实验 2：【有防护模式】(经过 SQLGuardian / ContradictionDetector 门禁)
        # ==============================================================================
        print("\n" + "="*70)
        print("[TEST-RESULT] [PROTECTED-MODE] Interception & Self-Healing Pipeline:")
        
        # 阶段 A：门禁前置 AST 静态检测
        violation = ContradictionDetector.detect(unprotected_bad_sql, archetypes=[missing_companion_archetype])
        assert violation is not None, "门禁必须在物理执行前将坏 SQL 截杀！"
        print(f"   [INTERCEPTED] Successfully blocked bad SQL! Reason: {violation.message}")
        print(f"   [SAFETY-GUARD] Bad query blocked before reaching ClickHouse/DB!")

        # 阶段 B：反思自愈环（Reflection Loop）根据门禁诊断，将其自愈重构为正确的【跨行对撞子查询】
        healed_good_sql = """
        SELECT setl_id, psn_name, hilist_name, det_item_fee_sumamt 
        FROM fqz_fymx_test 
        WHERE hilist_name LIKE '%麻醉%' 
          AND setl_id NOT IN (
              SELECT setl_id FROM fqz_fymx_test WHERE hilist_name LIKE '%手术%'
          )
        """
        
        # 门禁对自愈后的合规 SQL 亮绿灯放行
        assert ContradictionDetector.detect(healed_good_sql, archetypes=[missing_companion_archetype]) is None

        # 阶段 C：下发合规 SQL 执行
        cursor.execute(healed_good_sql)
        protected_results = cursor.fetchall()

        print("\n[TEST-RESULT] [PROTECTED-MODE] Healed Query Results:")
        for row in protected_results:
            print(f"   -> [TRUE-VIOLATION] setl_id: {row[0]} | patient: {row[1]} | item: {row[2]} | fee: {row[3]}")

        accused_names_protected = [row[1] for row in protected_results]
        assert "张三" not in accused_names_protected, "合规病人张三被成功保护，没有被误判！"
        assert "李四" in accused_names_protected, "真实骗保病人李四被精准命中！"
        print("   [SUCCESS] Perfect result: Zhang San (legitimate) exonerated, Li Si (fraud) accurately caught!")
        print("="*70 + "\n")
