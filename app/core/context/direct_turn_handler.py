"""
[SPEC-227 / Matt Pocock Deep Module] 直通非取证任务治理门面 (Direct Turn Handler)

收敛所有的非数据取证型直通逻辑（便签记录/撤销、长期记忆回溯、阶段性工作底稿聚合、
用户画像与偏好沉淀、AST 安全阻断、通用问候/闲聊）。
对外仅暴露极窄接口，彻底将 agent_graph 与底层的字符串拼接、文件 I/O、闲聊模板解耦。
"""

from __future__ import annotations
from typing import Any, Dict, Mapping, Optional, Sequence
from app.core.context.direct_turn_dispatcher import (
    DirectTurnContext,
    direct_turn_dispatcher,
    append_audit_note_to_file as _append_to_audit_notes_file,
)


def handle_direct_turn(
    *,
    user_input: str,
    turn_type: str,
    key_entities: Sequence[str],
    state: Mapping[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    处理非数据取证类直通分支任务。
    
    :return: 若命中直通分支，返回状态更新字典；若属于常规 QUERY 取证任务，返回 None 允许进入漏斗。
    """
    meta: Dict[str, Any] = dict(metadata or state.get("metadata") or {})
    meta["user_question"] = user_input
    meta["turn_type"] = turn_type

    ctx = DirectTurnContext(
        user_input=user_input,
        turn_type=turn_type,
        key_entities=key_entities,
        state=state,
        metadata=meta,
    )
    return direct_turn_dispatcher.dispatch(ctx)
