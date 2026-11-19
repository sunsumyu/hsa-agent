"""
app/reporting/reporter_node_orchestrator.py
===========================================
[Matt Pocock Deep Module & SSOT]
报告节点执行协同器 (ReporterNodeOrchestrator)。

核心职责：
1. 直通汇编分流：识别 metadata 中的 synthesis_done，直通组装阶段性底稿与便签回溯结果；
2. 原始证据解析与客观统计度量计算 (AuditMetricEvaluator)；
3. 结论自愈与仲裁 (conclusion_orchestrator)；
4. 结构化报告多格式与偏好渲染 (report_renderer)；
5. 语义对齐防偏离核验 (booster.verify_semantic_alignment)；
6. 轮次生命周期提交补丁装配 (turn_lifecycle)。
"""

from typing import Dict, Any, Optional
from loguru import logger
from langchain_core.messages import AIMessage

from app.core.booster import booster
from app.core.registry.schema_registry import schema_registry
from app.reporting.report_renderer import report_renderer
from app.reporting.audit_metric_evaluator import AuditMetricEvaluator
from app.reporting.conclusion_orchestrator import resolve_conclusion
from app.reporting.turn_lifecycle import (
    resolve_format_preference,
    extract_key_entities,
    create_turn_commit_patch,
)


def handle_synthesis_bypass(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    [SPEC-227] 直通底稿/便签/回溯/经验沉淀渲染。
    若 metadata 中包含 synthesis_done，直接组装最终回复并生成空度量生命周期提交补丁。
    """
    metadata = state.get("metadata") or {}
    if not metadata.get("synthesis_done"):
        return None

    rendered_content = metadata.get("direct_response")
    if not rendered_content:
        messages = state.get("messages", [])
        last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        rendered_content = str(getattr(last_ai, "content", "")) if last_ai else "核查完成"

    current_q = state.get("current_turn_query") or metadata.get("user_question") or "医保审计任务"

    commit_patch = create_turn_commit_patch(
        state=state,
        user_query=current_q,
        summary_conclusion=rendered_content[:150],
        hard_count=0,
        hard_sum=0.0,
        key_entities=[],
        core_sql=state.get("sql_query", "")
    )

    return {
        "messages": [AIMessage(content=rendered_content)],
        **commit_patch
    }


async def orchestrate_standard_report(
    state: Dict[str, Any],
    config: Any,
    max_retries: int = 1
) -> Dict[str, Any]:
    """
    常规物理取证场景下的报告组装生命周期。
    """
    raw_data_list = report_renderer.clean_and_parse_raw_data(state.get("raw_data"))
    hard_count, hard_sum = AuditMetricEvaluator.extract_totals(raw_data_list)

    # 1. 仲裁与生成审计结论 [Matt Pocock Deep Module: conclusion_orchestrator]
    llm_conclusion, is_restricted = await resolve_conclusion(
        state=state,
        raw_data_list=raw_data_list,
        hard_count=hard_count,
        hard_sum=hard_sum,
        config=config,
        max_retries=max_retries,
    )

    metadata = state.get("metadata") or {}
    user_question = metadata.get("user_question") or "医保专项审计"

    # 2. 提取最后一条 AI 消息元数据作为溯源证据
    messages = state.get("messages", [])
    last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    audit_meta = getattr(last_ai, "additional_kwargs", {}) if last_ai else {}

    methodology = state.get("methodology", "基础核查逻辑")
    execution_trace = state.get("execution_trace") or []
    format_pref = resolve_format_preference(state)

    # 3. 渲染结构化报告
    rendered = report_renderer.render(
        user_question=user_question,
        llm_conclusion=llm_conclusion,
        raw_data=raw_data_list,
        sql_query=state.get("sql_query"),
        sql_history=state.get("sql_history", []),
        methodology=methodology,
        table_info=f"{schema_registry.get_main_table()}",
        total_amount=hard_sum,
        finding_count=hard_count,
        execution_trace=execution_trace,
        audit_metadata=audit_meta,
        semantic_alignment=metadata.get("semantic_alignment"),
        raw_data_str=state.get("raw_data"),
        is_restricted=is_restricted,
        format_preference=format_pref
    )

    # 4. 语义偏离核验
    if not is_restricted:
        is_aligned, _ = booster.verify_semantic_alignment(state.get("sql_query"), llm_conclusion)
        if not is_aligned:
            logger.warning("🚨 [SEMANTIC_MISMATCH] 报告语义偏离")

    # 5. [SPEC-227 Turn Commit Hook] 提取关键实体并沉淀为不可变审计发现
    key_entities = extract_key_entities(raw_data_list)
    commit_patch = create_turn_commit_patch(
        state=state,
        user_query=user_question,
        summary_conclusion=llm_conclusion,
        hard_count=hard_count,
        hard_sum=hard_sum,
        key_entities=key_entities,
        core_sql=state.get("sql_query")
    )

    return {
        "structured_report": rendered,
        "messages": [AIMessage(content=rendered.markdown)],
        **commit_patch
    }


async def orchestrate_reporter_node(
    state: Dict[str, Any],
    config: Any,
    max_retries: int = 1
) -> Dict[str, Any]:
    """
    顶层 Reporter 节点统一编排入口。
    """
    logger.info(">>> [REPORTER] 正在执行渲染任务...")

    # 优先检查阶段性底稿直通分支
    bypass_result = handle_synthesis_bypass(state)
    if bypass_result is not None:
        return bypass_result

    # 执行标准审计报告渲染生命周期
    return await orchestrate_standard_report(state, config, max_retries=max_retries)
