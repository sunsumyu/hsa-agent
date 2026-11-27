"""
tests/unit/test_contradiction_self_healing_simulation.py
=========================================================
多智能体协同与自愈闭环端到端全真模拟测试套件
业务场景：男性参保人违规结算女性专属宫内节育器 (EXCLUSION_MUTEX)

全流程仿真：
  Step 1: Planner 规划意图与认知解耦 (锁定男性主体与互斥原型)
  Step 2: Coder 生成反向排除二元枚举的恒假坏 SQL
  Step 3: AST 静态门禁 (ContradictionDetector / Gate 2) 在物理执行前强行截杀
  Step 4: 状态机条件路由 (route_sqlexec_post) 拒绝死循环，将控制权转交 CRITIC
  Step 5: Critic 反思引擎 (AuditReflectionEngine) 进行 Token 脱水与领域定向纠偏
  Step 6: 状态机条件路由 (route_critic_post) 将诊断指令打回 SQLEXEC (Coder)
  Step 7: Coder 吸收极简纠偏指令，重新生成正向筛选合法 SQL，门禁全绿通过
  Step 8: 状态机条件路由锁定物理取证成功，直接导向 CONSOLIDATOR 闭环沉淀
  Step 9: 逃生舱熔断测试 (重试耗尽时降级为受限报告模式，杜绝无限死循环)
"""

import pytest
from loguru import logger

from app.core.planning.audit_intent_planner import AuditIntentPlanner, AuditArchetype
from app.core.guardrails.contradiction_detector import ContradictionDetector
from app.core.context.gates import QualityGate
from app.agents.coder_quality_guard import check_pre_execution_gate
from app.orchestration.graph_route_coordinator import route_sqlexec_post, route_critic_post
from app.core.reflection.audit_reflection_engine import AuditReflectionEngine
from app.agents.reflection_diagnostic_policy import ReflectionDiagnosticPolicy


@pytest.fixture(autouse=True)
def setup_test_logger():
    """配置结构化日志输出格式，确保控制台输出清晰的可视化跟踪"""
    logger.info("================================================================================")
    yield
    logger.info("================================================================================\n")


def test_step_01_planner_cognitive_decoupling():
    """
    Step 1: Planner 意图规划与认知解耦测试
    验证：大模型在生成 SQL 前，必须先通过意图规划器锁定主体属性与业务原型，严禁直连 SQL。
    """
    user_query = "请排查全省范围内男性参保人结算女性专属宫内节育器的违规医保基金使用明细"
    logger.info(f"📥 [Step 1: 用户输入] {user_query}")

    intent = AuditIntentPlanner.extract_intent(user_query)

    logger.info(f"🧠 [Step 1: 规划输出] 主体: '{intent.audit_subject}' | 特征: '{intent.violation_feature}'")
    logger.info(f"🏷️  [Step 1: 原型判定] 业务原型: {intent.archetype.value} | 目标性别代码: '{intent.target_gender}'")
    logger.info(f"📝 [Step 1: 强约束指引] {intent.enforcement_guidance}")

    assert intent.target_gender == "1", "违规主体必须锁定为男性 (gend='1')"
    assert "男" in intent.audit_subject
    assert "节育" in intent.violation_feature
    assert intent.archetype == AuditArchetype.EXCLUSION_MUTEX, "必须匹配为互斥排他业务原型"
    logger.success("✅ Step 1: Planner 意图规划与认知解耦校验 100% 通过！")


def test_step_02_ast_intercepts_binary_enum_contradiction():
    """
    Step 2 & 3: Coder 生成反模式恒假 SQL，AST 静态门禁在物理执行前精准拦截
    验证：即使模型写出合法 ClickHouse 语法，AST 也必须在发出 DB 查询前发现二元枚举被全排除。
    """
    # 模拟大模型混淆主客体生成的恒假坏 SQL：同时排除了 1（男）和 2（女）
    bad_sql = """
    SELECT psn_no, hilist_name, det_item_fee_sumamt 
    FROM fqz_fymx_test 
    WHERE hilist_name LIKE '%宫内节育%' 
      AND gend NOT LIKE '1%' 
      AND gend != '2'
    """
    logger.info("🤖 [Step 2: Coder 生成 SQL（含主客体混淆）]:")
    logger.info(f"    {bad_sql.strip()}")

    # 1. 纯 AST 静态恒假检测器扫描
    violation = ContradictionDetector.detect(bad_sql)
    assert violation is not None, "AST 恒假检测器必须捕获到二元枚举矛盾！"
    logger.warning(f"🚨 [Step 3: AST 恒假违规拦截] 冲突字段: `{violation.column}` | 冲突谓词: {violation.conflicting_predicates}")
    logger.warning(f"⚠️  [Step 3: 拦截详讯] {violation.message}")
    assert violation.column.lower() == "gend"

    # 2. Gate 2 语义守卫包装器审查
    dummy_state = {"methodology": "性别排他冲突筛查", "user_query": "男性使用宫内节育器"}
    gate_res = QualityGate.validate_sql_semantics(dummy_state, bad_sql)
    assert not gate_res.get("passed", True), "Gate 2 语义审查必须亮红灯！"
    logger.info(f"🛡️  [Step 3: Gate 2 拦截诊断提示] {gate_res.get('error')}")

    # 3. 工具执行前置门控拦截 (check_pre_execution_gate)
    tool_calls = [{"name": "execute_audit_sql", "args": {"sql": bad_sql}}]
    pre_gate = check_pre_execution_gate(tool_calls, dummy_state)
    assert not pre_gate.passed, "执行前置门禁必须拦截，阻止 SQL 发往 ClickHouse 数据库！"
    logger.success("✅ Step 2 & 3: AST 门禁在物理执行前截杀恒假 SQL，成功阻断物理无效查询！")


def test_step_04_route_sqlexec_to_critic():
    """
    Step 4: 状态机条件路由 (route_sqlexec_post) 测试
    验证：当执行拦截发生时，系统严禁直接死循环重试，必须由路由引流至 CRITIC。
    """
    state_after_intercept = {
        "error_log": "【静态语义恒假拦截】字段 `gend` 是二元枚举属性，但在查询中同时排除了所有取值 ['1', '2']",
        "retry_count": 0,
        "has_error": True,
        "sql_validated": False,
        "raw_data": ""
    }
    logger.info(f"📊 [Step 4: 当前 State] error_log 存在 | retry_count={state_after_intercept['retry_count']}")

    next_node = route_sqlexec_post(state_after_intercept, max_retries=2)
    logger.info(f"🚦 [Step 4: SQLEXEC 路由决策] 下一跳 -> {next_node}")

    assert next_node == "CRITIC", "发生执行拦截且 retry_count < max_retries 时，下一跳必须是 CRITIC！"
    logger.success("✅ Step 4: 路由中心成功将状态机导向 CRITIC 审校节点，杜绝 Coder 盲目自循环！")


def test_step_05_critic_dehydrates_error_into_actionable_prompt():
    """
    Step 5: Critic 反思引擎脱水与业务纠偏测试
    验证：Critic 绝不回传复杂 AST 错误栈，而是根据业务原型（EXCLUSION_MUTEX）输出极简修正指令。
    """
    bad_sql = "SELECT * FROM fqz_fymx_test WHERE hilist_name LIKE '%节育%' AND gend NOT LIKE '1%' AND gend != '2'"
    intent = AuditIntentPlanner.extract_intent("男性使用宫内节育器")
    ast_error = "【静态语义恒假拦截】字段 `gend` 是二元枚举属性，但在查询中同时排除了所有取值 ['1', '2']"

    logger.info("🕵️  [Step 5: Critic 接收原始技术报错]:")
    logger.info(f"    {ast_error}")

    # 调用底层闭环反思自愈引擎 (Evaluator-Optimizer)
    refl_res = AuditReflectionEngine.evaluate_execution(
        sql=bad_sql,
        row_count=0,
        intent=intent,
        error_msg=ast_error
    )

    logger.info(f"💡 [Step 5: Critic 诊断反馈 (Token 脱水)]:\n    {refl_res.diagnostic_feedback}")
    logger.info(f"🔧 [Step 5: 建议纠偏动作]:\n    {refl_res.suggested_correction}")

    assert refl_res.needs_retry is True, "必须触发模型重试"
    assert "恒假" in refl_res.diagnostic_feedback or "性别互斥" in refl_res.diagnostic_feedback
    assert "移除" in refl_res.suggested_correction or "正向" in refl_res.suggested_correction
    logger.success("✅ Step 5: Critic 完成技术报错到业务极简指令的高内聚脱水！")


def test_step_06_route_critic_back_to_sqlexec():
    """
    Step 6: Critic 条件路由 (route_critic_post) 测试
    验证：由于报错是具体的 SQL 语义/语法错误（而非顶层意图方法论错误），下一跳必须精准打回 SQLEXEC。
    """
    state_after_critic = {
        "error_log": "[CRITIC 反馈] 【反思自愈诊断】检测到静态语义门禁拦截。请检查 WHERE 条件，切勿对同一枚举字段同时排除多个互斥取值！",
        "retry_count": 1
    }

    next_node = route_critic_post(state_after_critic)
    logger.info(f"🚦 [Step 6: CRITIC 路由决策] 下一跳 -> {next_node}")

    assert next_node == "SQLEXEC", "SQL 执行层面错误，Critic 审校完毕后必须打回 SQLEXEC 重新编码！"
    logger.success("✅ Step 6: 路由中心准确将纠偏任务打回 SQLEXEC 节点！")


def test_step_07_coder_self_healing_and_gate_pass():
    """
    Step 7 & 8: Coder 吸收纠偏指令，生成合规正向筛选 SQL，门禁全绿放行至 CONSOLIDATOR
    验证：自愈改写后的 SQL 必须通过 AST 检验，且状态机能够顺利流向经验归档节点。
    """
    # 模拟 Coder 吸收纠偏提示后生成的完美 SQL：正向筛选男性 gend LIKE '1%'
    healed_sql = """
    SELECT 
        psn_no,
        replace(hilist_name, '\t', '') AS item_name,
        count(*) AS item_cnt,
        round(sum(det_item_fee_sumamt), 2) AS item_fee
    FROM fqz_fymx_test
    WHERE gend LIKE '1%'
      AND hilist_name LIKE '%宫内节育%'
    GROUP BY psn_no, item_name
    """
    logger.info("🛠️  [Step 7: Coder 自愈重写生成合规 SQL]:")
    logger.info(f"    {healed_sql.strip()}")

    # 1. 重新进行 AST 检验
    violation = ContradictionDetector.detect(healed_sql)
    assert violation is None, "自愈后的 SQL 绝对不能再触发恒假拦截！"
    logger.info("✨ [Step 7: AST 门禁检测] 无逻辑矛盾，静态语法树检查 100% 通过！")

    # 2. 前置执行门禁放行
    dummy_state = {"methodology": "性别排他冲突筛查", "user_query": "男性使用宫内节育器"}
    tool_calls = [{"name": "execute_audit_sql", "args": {"sql": healed_sql}}]
    pre_gate = check_pre_execution_gate(tool_calls, dummy_state)
    assert pre_gate.passed is True, "自愈后的执行前置门禁必须顺利 PASS！"

    # 3. 模拟 ClickHouse 物理执行成功拿到取证数据
    state_after_healed_exec = {
        "sql_query": healed_sql,
        "sql_validated": True,
        "raw_data": "[{'psn_no': 'P0001', 'item_name': '左炔诺孕酮宫内节育系统', 'item_fee': 5880.0}]",
        "error_log": None,
        "retry_count": 1
    }

    # 4. 路由判定：取证成功且无错误，直接前往 CONSOLIDATOR，斩断多余 LLM 乒乓
    final_node = route_sqlexec_post(state_after_healed_exec, max_retries=2)
    logger.info(f"🎯 [Step 8: 物理取证完成路由决策] 下一跳 -> {final_node}")

    assert final_node == "CONSOLIDATOR", "取证成功且无错误时，直接走向 CONSOLIDATOR 组织经验沉淀！"
    logger.success("✅ Step 7 & 8: 自愈改写成功，门禁全绿放行，取证完成直接闭环交付！")


def test_step_09_escape_hatch_circuit_breaker():
    """
    Step 9: 逃生舱熔断与受限模式降级测试 (防无限死循环)
    验证：当重试次数达到刚性上限（如 retry_count >= max_retries）时，系统绝不卡死，强行熔断降级。
    """
    logger.info("🚨 [Step 9: 极限边界测试 - 模拟模型顽固错误达到最大重试上限]")
    policy = ReflectionDiagnosticPolicy(max_retries=2)

    # 模拟重试达到上限
    current_retry = 2
    is_triggered = policy.is_escape_hatch_triggered(current_retry)
    logger.warning(f"🛑 [Step 9: 逃生舱判定] 当前重试次数: {current_retry} | 触发熔断: {is_triggered}")
    assert is_triggered is True, "重试超限时必须触发逃生舱熔断！"

    # 生成逃生舱降级指令
    escape_msg = policy.generate_escape_hatch_message()
    logger.info(f"📋 [Step 9: 降级报告指示文本]:\n{escape_msg.content}")
    assert "受限核查报告" in escape_msg.content or "降级报告模式" in escape_msg.content

    # 路由防御性验证：超限后禁止再流向 CRITIC
    exhausted_state = {
        "error_log": "顽固错误持续未解",
        "retry_count": 2, # 已满
        "has_error": True,
        "sql_validated": False,
        "raw_data": ""
    }
    terminal_route = route_sqlexec_post(exhausted_state, max_retries=2)
    logger.info(f"🛑 [Step 9: 熔断状态机路由] 下一跳 -> {terminal_route} (不再允许流向 CRITIC)")
    assert terminal_route != "CRITIC", "重试超限时严禁再次进入自愈循环，必须直通收尾节点！"
    logger.success("✅ Step 9: 逃生舱熔断机制生效，彻底封死 Agent 乒乓死循环风险！")
