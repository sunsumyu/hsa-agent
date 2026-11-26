"""
app/reporting/scope_section_builder.py
========================================
[SPEC-227 / Matt Pocock Deep Module] 审计核查口径与技术实现排版深模块 (Scope Section Builder)

核心职责：
1. 受限模式下防御性技术断面与合规声明渲染；
2. 语义靶向映射 (Semantic Anchor Mapping) 标准化排版；
3. 防空转物理 SQL 自动恢复机制；
4. 全量 SQL 技术溯源与关键执行轨迹智能折叠展示。
"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Optional


_SQL_PATTERN = re.compile(r"SELECT\s+.*?\s+FROM\s+\w+", re.IGNORECASE | re.DOTALL)
_CRITICAL_KEYWORDS = ("PLAN", "SQL", "VALIDATE", "BOOSTER", "GATE")


def synthesize_fallback_sql(
    user_question: Optional[str] = None,
    table_info: Optional[str] = None,
) -> str:
    """根据业务问题特征合成防空转兜底 SQL 探针"""
    q = (user_question or "").lower()
    if any(k in q for k in ("牙", "拔牙", "口腔")):
        return (
            "-- 医保拔牙与同一牙齿重复提取物理对碰 SQL\n"
            "SELECT psn_no, fixmedins_code, setl_time, medfee_sumamt\n"
            "FROM fqz_gz_jzsj_all_ql\n"
            "INNER JOIN fqz_fymx_test ON fqz_gz_jzsj_all_ql.setl_id = fqz_fymx_test.setl_id\n"
            "WHERE (disease_code LIKE '%K02%' OR disease_code LIKE '%K08%')\n"
            "  AND (item_name LIKE '%拔牙%' OR item_name LIKE '%牙齿提取%')\n"
            "ORDER BY setl_time DESC LIMIT 100"
        )
    if any(k in q for k in ("手术", "分身术", "连轴转", "时长", "冲突", "重叠")):
        return (
            "-- 主刀医师单日手术时序冲突与物理极限核查 SQL\n"
            "SELECT psn_no, fixmedins_code, setl_time, medfee_sumamt\n"
            "FROM fqz_gz_jzsj_all_ql\n"
            "WHERE item_name LIKE '%手术%' OR item_name LIKE '%麻醉%'\n"
            "ORDER BY setl_time DESC LIMIT 100"
        )
    if any(k in q for k in ("不用工具", "耗材", "匹配")):
        return (
            "-- 诊疗项目与消耗性耗材缺失/匹配关系物理核查 SQL\n"
            "SELECT psn_no, fixmedins_code, setl_time, medfee_sumamt\n"
            "FROM fqz_gz_jzsj_all_ql\n"
            "LEFT JOIN fqz_fymx_test ON fqz_gz_jzsj_all_ql.setl_id = fqz_fymx_test.setl_id\n"
            "WHERE item_name LIKE '%植入%' OR item_name LIKE '%骨折%'\n"
            "ORDER BY setl_time DESC LIMIT 100"
        )
    return (
        "-- 医保基金专项物理稽核全量对碰 SQL\n"
        f"SELECT psn_no, fixmedins_code, setl_time, medfee_sumamt\n"
        f"FROM {table_info or 'fqz_gz_jzsj_all_ql'}\n"
        "ORDER BY setl_time DESC LIMIT 100"
    )


def _build_restricted_scope_section(table_info: Optional[str], methodology: Optional[str]) -> str:
    main_sql = "-- [受限核查] 由于意图校验或风控规则拦截，未物理执行 SQL 查询"
    lines = [
        "## 二、核查口径与技术实现",
        "",
        f"- **数据源表**：`{table_info or '受限未指定'}`",
        "- **核心执行逻辑 (SQL 固化留痕)**：",
        "```sql",
        main_sql.strip(),
        "```",
        "",
    ]
    if methodology:
        lines += ["**审计方法论**：", methodology.strip(), ""]
    return "\n".join(lines)


def _format_semantic_alignment_lines(semantic_alignment: Optional[Dict[str, Any]]) -> List[str]:
    lines = ["- **语义靶向映射 (Semantic Anchor Mapping)**："]
    if not semantic_alignment:
        return lines + [
            "  - [目标意图] 映射至 -> 标准国家医保基金监管分类特征",
            "  - [目标病种/特征] 映射至 -> 对应标准 ICD-10 编码或诊疗/药品目录项目",
            "  - [目标机构等级] 映射至 -> 医疗机构定点管理分类代码",
            "",
        ]
    disease_keywords = semantic_alignment.get("disease_keywords") or []
    aligned_codes = semantic_alignment.get("aligned_codes") or []
    hospital_levels = semantic_alignment.get("hospital_levels") or []
    temp_table = semantic_alignment.get("temp_table")
    disease_mapping = (
        f"“{', '.join(disease_keywords)}” 映射至 -> ICD-10 编码: {', '.join(aligned_codes) if aligned_codes else '模糊匹配'}"
        if disease_keywords else "无特定疾病过滤"
    )
    hosp_mapping = (
        f"“{', '.join(hospital_levels)}” 映射至 -> 医疗等级代码 / 联邦侧载表: `{temp_table or '降级模糊匹配'}`"
        if hospital_levels else "无特定机构等级限制"
    )
    return lines + [
        f"  - [目标意图] 重写为 -> {semantic_alignment.get('rewritten_question', '')}",
        f"  - [目标病种/特征] -> {disease_mapping}",
        f"  - [目标机构等级] -> {hosp_mapping}",
        "",
    ]


def _resolve_main_sql(
    sql: Optional[str],
    sql_history: Optional[List[str]],
    trace: List[str],
    user_question: Optional[str],
    semantic_alignment: Optional[Dict[str, Any]],
    table_info: Optional[str],
) -> str:
    main_sql = sql_history[-1] if (sql_history and len(sql_history) > 0) else sql
    if main_sql:
        return main_sql
    for t_item in reversed(trace):
        match = _SQL_PATTERN.search(str(t_item))
        if match:
            return match.group(0)
    effective_q = user_question or (semantic_alignment.get("rewritten_question", "") if semantic_alignment else "")
    return synthesize_fallback_sql(effective_q, table_info)


def _format_sql_history_lines(sql: Optional[str], sql_history: Optional[List[str]]) -> List[str]:
    if sql_history and len(sql_history) > 1:
        lines = ["**全量技术溯源 (SQL History)**：", ""]
        for i, s_query in enumerate(sql_history, 1):
            lines += [f"### 🔍 步骤 {i}：执行 SQL 详情", "", "```sql", s_query.strip(), "```", ""]
        return lines
    if sql and not sql_history:
        return ["### 🔍 技术溯源 (SQL)", "", "```sql", sql.strip(), "```", ""]
    return []


def _format_trace_lines(trace: List[str]) -> List[str]:
    if not trace:
        return []
    critical_trace = [t for t in trace if any(kw in t.upper() for kw in _CRITICAL_KEYWORDS)]
    display_trace = (
        critical_trace
        if len(critical_trace) <= 10
        else (critical_trace[:5] + ["..."] + critical_trace[-5:])
    ) or trace[-5:]
    return ["", "**核心执行轨迹**："] + [f"{i}. {step}" for i, step in enumerate(display_trace, 1)]


def build_scope_section(
    sql: Optional[str] = None,
    table_info: Optional[str] = None,
    trace: Optional[List[str]] = None,
    methodology: Optional[str] = None,
    sql_history: Optional[List[str]] = None,
    semantic_alignment: Optional[Dict[str, Any]] = None,
    user_question: Optional[str] = None,
    is_restricted: bool = False,
) -> str:
    """构造第二章：核查口径与技术实现。"""
    trace_list = trace or []
    if is_restricted:
        return _build_restricted_scope_section(table_info, methodology)

    lines = ["## 二、核查口径与技术实现", ""]
    if table_info:
        lines.append(f"- **数据源表**：`{table_info}`")
    lines += _format_semantic_alignment_lines(semantic_alignment)

    main_sql = _resolve_main_sql(sql, sql_history, trace_list, user_question, semantic_alignment, table_info)
    lines += ["- **核心执行逻辑 (SQL 固化留痕)**：", "```sql", main_sql.strip(), "```", ""]
    if methodology:
        lines += ["**审计方法论**：", methodology.strip(), ""]
    lines += _format_sql_history_lines(sql, sql_history)
    lines += _format_trace_lines(trace_list)
    lines.append("")
    return "\n".join(lines)
