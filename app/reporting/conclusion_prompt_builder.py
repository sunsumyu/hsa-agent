"""
app/reporting/conclusion_prompt_builder.py
=========================================
[Matt Pocock Deep Module] 审计结论 LLM Prompt 组装与事实强制对齐深模块

核心职责：
1. 封装针对受限执行与逃生舱的防御性指引 (Fail-Closed 物理异常声明)
2. 封装零检出合规场景的时序防守深度与扫描基数声明
3. 封装正向检出场景的事实强制对齐与金额硬约束
4. 格式化结合全局 CONCLUSION_PROMPT 模板
"""

from __future__ import annotations

from typing import List, Optional


def build_conclusion_prompt(
    user_question: str,
    methodology: str,
    execution_trace: List[str],
    hard_count: int,
    hard_sum: float,
    rewritten_question: Optional[str] = None,
    is_restricted: bool = False,
) -> str:
    """构造事实强制对齐且逻辑白盒化之 LLM 结论生成 Prompt"""

    if is_restricted:
        defense_instruction = (
            "5. **【Fail-Closed 物理异常声明】（绝对红线）**：当前核查由于物理规则拦截、底层语法异常或超时导致执行受限，"
            "你必须客观阐述执行受限的技术事实与物理断面，严禁推断业务合规！\n"
        )
        data_summary = "【执行受限】由于规则或执行异常，未取得有效物理查询结果集。"
    elif hard_count == 0:
        defense_instruction = (
            "5. **【时序防守深度与数据支撑型声明】**：当前核查物理过滤结果为 0 条。你必须客观陈述物理全量过滤未发现违规记录的事实，并在结论末尾追加关于时序边缘场景的防御性建议。\n"
            "   同时，你必须明确区分“全局扫描基数”与“违规命中数”。格式必须为：“本次核查对底层表进行了全量扫描，在当前严苛的审计特征过滤条件下，最终命中的违规异常明细记录为 0 条。”\n"
        )
        data_summary = f"本次核查对底层表进行了全量扫描，最终命中的违规异常明细记录为 0 条，涉及金额 ¥{hard_sum:,.2f}"
    else:
        defense_instruction = f"5. **事实强制对齐**：当前发现 {hard_count} 条记录，结论必须明确指出违规嫌疑，严禁敷衍。\n"
        data_summary = f"共穿透扫描相关记录 {hard_count} 条，涉及金额 ¥{hard_sum:,.2f}"

    from app.core.prompts import CONCLUSION_PROMPT

    prompt_msgs = CONCLUSION_PROMPT.format_messages(
        user_question=rewritten_question or user_question,
        methodology=methodology[:600],
        execution_trace='; '.join(execution_trace[-5:]) if execution_trace else '已完成全路径核查',
        data_summary=data_summary,
        defense_instruction=defense_instruction,
    )
    return str(prompt_msgs[0].content) if prompt_msgs else ""
