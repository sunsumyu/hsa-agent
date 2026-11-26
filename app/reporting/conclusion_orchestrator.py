"""
app/reporting/conclusion_orchestrator.py
==========================================
[SPEC-227 / Matt Pocock Deep Module] 审计结论仲裁与分流深模块 (Audit Conclusion Orchestrator)

核心职责：
1. 受限状态与逃生舱判定：基于事实证据与重试状态确定是否进入受限核查渲染模式。
2. 多级确定性分流仲裁：
   - 快速路由 (Fast Route)：直接套用标准化规则模板，秒级响应；
   - Coder 结论就地复用：识别 Coder 输出的高质量核查指标，杜绝二次 LLM 重复调用；
   - 零违规合规基线直通：检出为 0 且证据有效时，使用确定性合规模板；
   - LLM 动态兜底生成：在无法直通时调用统一模型服务，并提供优雅的异常安全兜底。
3. 严格遵循 Pocock Deep Module 原则，对外仅暴露单一异步接口 resolve_conclusion。
"""

from __future__ import annotations
from typing import Any, Dict, List, Mapping, Optional, Tuple
from loguru import logger
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.core.config import settings


_RICH_SUMMARY_KEYWORDS = ("审计指标", "取证结果", "统计结果", "核查结果", "##")
_ZERO_FINDING_TEMPLATE = (
    "本次核查对底层物理数据表进行了全量扫描排查。在当前严格的审计特征与条件过滤下，"
    "未发现任何违规异常单据（违规记录数 0 条，涉及金额 ¥0.00），各项指标均处于客观合规基线范围内。"
)


async def resolve_conclusion(
    state: Mapping[str, Any],
    raw_data_list: List[Dict[str, Any]],
    hard_count: int,
    hard_sum: float,
    config: Optional[RunnableConfig] = None,
    max_retries: Optional[int] = None,
) -> Tuple[str, bool]:
    """
    仲裁并生成审计结论。
    
    :param state: LangGraph 审计全局状态
    :param raw_data_list: 已清洗的标准结构化数据流水
    :param hard_count: 检出条数
    :param hard_sum: 涉及总金额
    :param config: RunnableConfig
    :param max_retries: 最大重试上限（若不传则从 settings.max_agent_retries 取）
    :return: (llm_conclusion, is_restricted)
    """
    if max_retries is None:
        max_retries = min(getattr(settings, "max_agent_retries", 1), 1)

    error_log = str(state.get("error_log") or "")
    sql_query = state.get("sql_query")
    retry_count = int(state.get("retry_count") or 0)
    sql_validated = bool(state.get("sql_validated", False))

    # [Matt Pocock 证据优先原则] 若已获取真实物理数据或已成功校验通过 SQL，绝不开启受限核查
    has_valid_evidence = bool(sql_query) and (bool(raw_data_list) or sql_validated)

    is_restricted = False
    if not has_valid_evidence:
        if (
            retry_count >= max_retries
            or "降级报告模式" in error_log
            or "REACHED_MAX_RETRIES" in error_log
            or not sql_validated
        ):
            is_restricted = True
            logger.warning("🚨 [ConclusionOrchestrator] 检测到执行受限/逃生舱触发，开启受限核查模式。")

    metadata = dict(state.get("metadata") or {})
    user_question = metadata.get("user_question") or "医保专项审计"
    methodology = state.get("methodology", "基础核查逻辑")
    execution_trace = state.get("execution_trace") or []
    fast_route_id = metadata.get("fast_route_id")

    # 提取最后一条 AI 消息
    messages = state.get("messages", [])
    last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    last_content = str(getattr(last_ai, "content", "") or "").strip()

    # 判定是否满足 Coder 高质量结论直接复用 (至少包含关键词且具备一定实质篇幅)
    has_rich_coder_summary = (
        bool(sql_query)
        and len(last_content) >= 50
        and not getattr(last_ai, "tool_calls", None)
        and any(k in last_content for k in _RICH_SUMMARY_KEYWORDS)
    )

    # 1. 快速路由直通分支
    if fast_route_id:
        from app.reporting.fast_route_conclusion import generate_fast_route_conclusion
        conclusion = generate_fast_route_conclusion(
            raw_data_list, hard_sum, hard_count, user_question
        )
        return conclusion, is_restricted

    # 2. Coder 结论就地复用分支
    if has_rich_coder_summary:
        logger.info("✨ [ConclusionOrchestrator] 检测到 Coder 已输出完整高质量审计结论，直接采纳，跳过独立 Reporter LLM 调用")
        return last_content, is_restricted

    # 3. 零违规合规基线直通分支
    if bool(sql_query) and hard_count == 0 and not is_restricted:
        logger.info("✨ [ConclusionOrchestrator] 零违规合规基线审计直通，使用确定性合规模板，跳过独立 Reporter LLM 调用")
        return _ZERO_FINDING_TEMPLATE, is_restricted

    # 4. 受限模式且无明确证据时的直接告知
    if is_restricted and not raw_data_list:
        fallback_msg = f"本次核查由于执行逻辑受限未产出确切违规结论。{error_log[:150]}" if error_log else "本次核查由于执行受限未产出确切违规结论。"
        return fallback_msg, True

    # 5. LLM 动态生成分支
    from app.reporting.report_renderer import report_renderer
    from app.core.llm_provider import llm_provider

    semantic_align = metadata.get("semantic_alignment") or {}
    rewritten_q = semantic_align.get("rewritten_question")
    prompt_text = report_renderer.prepare_conclusion_prompt(
        user_question,
        methodology,
        execution_trace,
        hard_count,
        hard_sum,
        rewritten_question=rewritten_q,
        is_restricted=is_restricted,
        retrieved_citations=state.get("retrieved_citations"),
    )

    try:
        response = await llm_provider.chat(
            role="reporter",
            messages=[HumanMessage(content=prompt_text)],
            config=config,
            state=state,
            max_tokens=400,
        )
        conclusion = str(response.content).strip()
    except Exception as e:
        logger.error(f"❌ [ConclusionOrchestrator] 结论生成失败: {e}")
        if is_restricted:
            conclusion = "本次核查由于逻辑受限未产出确切违规结论。"
        else:
            conclusion = f"本次核查扫描 {hard_count} 条记录，涉及金额 ¥{hard_sum:,.2f}。"

    return conclusion, is_restricted
