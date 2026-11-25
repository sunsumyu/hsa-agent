"""
app/core/state_governance.py
==============================
[Matt Pocock Deep Module] 审计会话状态生命周期与清洗标准化深模块

核心职责：
1. 标准化 AuditState 初始状态容器构造
2. 多轮对话中轮末/轮首无副作用清洗补丁生成 (Turn Reset Patch)
3. 状态对象日志打印脱敏与过长安全截断 (Safe Logging Snapshot)
"""

from __future__ import annotations
from typing import Dict, Any, Optional, Mapping
from langchain_core.messages import HumanMessage, BaseMessage


# 敏感信息关键字识别集合
_SENSITIVE_KEYS = {"certno", "tel", "phone", "mobile", "addr", "password", "token"}


def mask_sensitive_value(val: Any) -> str:
    """脱敏字符串值"""
    s = str(val or "")
    if len(s) <= 4:
        return "****"
    if len(s) <= 8:
        return s[:2] + "****" + s[-2:]
    return s[:3] + "****" + s[-4:]


def build_initial_audit_state(
    user_query: str,
    session_id: str,
    metadata: Optional[Mapping[str, Any]] = None,
    initial_messages: Optional[list[BaseMessage]] = None
) -> Dict[str, Any]:
    """
    构造规范且类型完备的初始 AuditState 容器。
    """
    merged_metadata = dict(metadata or {})
    merged_metadata.setdefault("user_question", user_query)
    
    messages = list(initial_messages or [])
    if not messages and user_query:
        messages.append(HumanMessage(content=user_query))

    return {
        "session_id": session_id,
        "messages": messages,
        "retry_count": 0,
        "plan_retry_count": 0,
        "sql_retry_count": 0,
        "tool_step_count": 0,
        "loop_count": 0,
        "error_log": None,
        "human_input": None,
        "is_awaiting_human": False,
        "next_step": "",
        "tasks": [],
        "sql_query": "",
        "sql_history": [],
        "raw_data": "",
        "sql_validated": False,
        "execution_trace": [],
        "schema_hint": None,
        "audit_findings": [],
        "structured_report": None,
        "audit_feedback": None,
        "methodology": "",
        "temp_table": None,
        "current_turn_query": user_query,
        "accumulated_findings": [],
        "turn_type": None,
        "audit_notes": [],
        "metadata": merged_metadata
    }


def create_turn_reset_patch(state: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """
    生成标准化的轮末/轮首无副作用状态清洗补丁。
    清空执行中间态与单轮触发器，保留长期事实与业务上下文。
    """
    st = state or {}
    metadata = dict(st.get("metadata") or {})

    # 清洗 metadata 中的单轮临时标记
    metadata["synthesis_done"] = False
    metadata["fast_route_id"] = None
    metadata["direct_response"] = None
    metadata["semantic_alignment"] = None
    metadata["execution_tier"] = None
    metadata["execution_plan"] = None

    return {
        "current_turn_query": None,
        "turn_type": None,
        "retry_count": 0,
        "plan_retry_count": 0,
        "sql_retry_count": 0,
        "tool_step_count": 0,
        "raw_data": "",
        "sql_query": "",
        "error_log": None,
        "execution_trace": [],
        "sql_validated": False,
        "metadata": metadata
    }


def filter_state_for_logging(
    state: Mapping[str, Any],
    max_raw_data_len: int = 200,
    max_sql_len: int = 500
) -> Dict[str, Any]:
    """
    生成安全的日志快照：过滤脱敏敏感字段，截断过长原始数据。
    """
    safe_state: Dict[str, Any] = {}
    for k, v in state.items():
        if k == "raw_data" and isinstance(v, str) and len(v) > max_raw_data_len:
            safe_state[k] = v[:max_raw_data_len] + f"...[TRUNCATED total={len(v)} chars]"
        elif k == "sql_query" and isinstance(v, str) and len(v) > max_sql_len:
            safe_state[k] = v[:max_sql_len] + f"...[TRUNCATED total={len(v)} chars]"
        elif k == "metadata" and isinstance(v, dict):
            safe_meta = {}
            for mk, mv in v.items():
                if any(sk in mk.lower() for sk in _SENSITIVE_KEYS):
                    safe_meta[mk] = mask_sensitive_value(mv)
                else:
                    safe_meta[mk] = mv
            safe_state[k] = safe_meta
        else:
            safe_state[k] = v
            
    return safe_state
