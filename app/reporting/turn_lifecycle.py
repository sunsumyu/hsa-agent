"""
app/reporting/turn_lifecycle.py
===============================
[Deep Module] 审计会话多轮生命周期与事实固化深模块。

设计哲学 (Matt Pocock Deep Module Principles):
    - 窄接口 (Narrow Interface):
      公开 `extract_key_entities`、`resolve_format_preference` 与 `create_turn_commit_patch`。
    - 消除图编排中枢的代码膨胀:
      将原先散落在 agent_graph.py reporter_node 中冗余 60+ 行的实体提取、
      偏好穿透、审计发现固化与轮末容器清洗（Turn Commit Hook）彻底收敛为单一事实源。
    - 纯函数与确定性:
      无副作用地产生标准化状态补丁（State Patch），确保多轮迭代中状态容器完全纯净。
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Sequence
from datetime import datetime


# 医保核心业务实体候选键优先级列表
_CORE_ENTITY_KEYS = ("fixmedins_name", "psn_name", "hilist_name", "medins_name")


def extract_key_entities(raw_data: Sequence[Any], max_records: int = 5) -> List[str]:
    """
    从原始取证数据前 N 条记录中提取关键业务实体（定点机构、参保人、重点药品等），
    并进行保留顺序的稳定去重。
    """
    if not raw_data or not isinstance(raw_data, (list, tuple)):
        return []

    entities: List[str] = []
    seen = set()

    for row in raw_data[:max_records]:
        if not isinstance(row, dict):
            continue
        for key in _CORE_ENTITY_KEYS:
            val = row.get(key)
            if val is not None:
                val_str = str(val).strip()
                if val_str and val_str not in seen:
                    seen.add(val_str)
                    entities.append(val_str)

    return entities


def resolve_format_preference(state: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    从用户画像与历史便签中解析报表呈现格式偏好 (LIST / TABLE)。
    优先级：metadata.user_profile.format > audit_notes 逆向扫描。
    """
    if not state:
        return None

    metadata = state.get("metadata") or {}
    user_pref = metadata.get("user_profile", {}).get("format")
    if user_pref:
        return str(user_pref).strip().upper()

    notes = state.get("audit_notes") or []
    for note in reversed(notes):
        note_str = str(note)
        if "无序列表" in note_str or "纯文字" in note_str:
            return "LIST"
        elif "表格" in note_str:
            return "TABLE"

    return None


def create_turn_commit_patch(
    state: Dict[str, Any],
    user_query: str,
    summary_conclusion: str,
    hard_count: int = 0,
    hard_sum: float = 0.0,
    key_entities: Optional[Sequence[str]] = None,
    core_sql: Optional[str] = None
) -> Dict[str, Any]:
    """
    [SPEC-227 Turn Commit Hook]
    将当前轮次的审计结论与度量沉淀为不可变发现，并生成标准化的轮末清洗字典。
    """
    st = state or {}
    metadata = dict(st.get("metadata") or {})

    turn_num = metadata.get("turn") or (len(st.get("accumulated_findings") or []) + 1)
    current_q = st.get("current_turn_query") or user_query

    turn_finding = {
        "turn": turn_num,
        "user_query": metadata.get("user_question", user_query),
        "resolved_query": current_q,
        "target_tables": metadata.get("target_tables") or [],
        "core_sql": core_sql if core_sql is not None else st.get("sql_query", ""),
        "affected_count": hard_count,
        "involved_amount": hard_sum,
        "key_entities": list(key_entities or []),
        "summary_conclusion": summary_conclusion[:150] if summary_conclusion else "",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    new_findings = list(st.get("accumulated_findings") or [])
    new_findings.append(turn_finding)

    from app.core.state import create_turn_reset_patch
    commit_patch = create_turn_reset_patch(st)
    commit_patch["accumulated_findings"] = new_findings
    return commit_patch
