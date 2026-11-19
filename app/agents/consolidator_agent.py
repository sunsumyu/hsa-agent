"""
app/consolidator_agent.py
=========================
[V150.0] 审计固化智能体 (Consolidator Agent)

负责：
1. 经验固化：将执行成功的审计路径（Task + SQL）保存至 FAISS 经验库。
2. 精准缓存：将用户原始问题与验证通过的 SQL 绑定，实现秒级二次命中。
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from loguru import logger
from app.memory.experience import experience_manager
from app.memory.semantic_memory import action_cache_manager

@dataclass(frozen=True)
class ConsolidationPayload:
    """[Matt Pocock 契约] 经验固化所需的强类型最小输入切片 (Input Slice)"""
    user_input: str
    tasks: List[str]
    sql: str
    sql_history: List[str]
    methodology: str
    is_successful: bool
    audit_timestamp: Optional[str] = None

def extract_consolidation_payload(state: Dict[str, Any]) -> ConsolidationPayload:
    """[纯函数提取器] 从状态字典中提取出固化所需切片，并判定有效性 (无副作用)"""
    tasks = state.get("tasks") or []
    sql = state.get("sql_query") or ""
    sql_history = state.get("sql_history") or []
    methodology = state.get("methodology") or ""
    
    metadata = state.get("metadata") or {}
    user_input = state.get("current_turn_query") or metadata.get("user_question") or ""
    
    if not user_input:
        from langchain_core.messages import HumanMessage
        for msg in reversed(state.get("messages") or []):
            if isinstance(msg, (HumanMessage, tuple)) or (hasattr(msg, "type") and msg.type in ("human", "user")):
                user_input = msg[1] if isinstance(msg, tuple) else str(msg.content)
                break

    has_error = bool(state.get("error_log"))
    raw_data = str(state.get("raw_data") or "")
    has_data = bool(raw_data.strip()) and "查询失败" not in raw_data
    has_valid_tasks = bool(tasks) and bool(sql or sql_history)

    is_successful = has_valid_tasks and (not has_error) and has_data

    return ConsolidationPayload(
        user_input=user_input,
        tasks=list(tasks),
        sql=sql,
        sql_history=list(sql_history),
        methodology=methodology,
        is_successful=is_successful,
        audit_timestamp=metadata.get("audit_timestamp"),
    )

class AuditConsolidatorAgent:
    def __init__(self):
        pass

    async def consolidate(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """对执行成功的路径进行多级固化 [V178.9]"""
        payload = extract_consolidation_payload(state)
        return await self.persist_payload(payload)

    async def persist_payload(self, payload: ConsolidationPayload) -> Dict[str, Any]:
        """[专职深模块执行] 仅对合法的强类型切片执行固化，消除隐式依赖"""
        if not payload.is_successful:
            logger.warning("🚫 [Consolidator] 审计逻辑未闭环或无数据，跳过经验沉淀")
            return {}

        logger.info(f"✨ [Consolidator] 正在为问题「{payload.user_input[:15]}...」执行经验沉淀...")

        # 1. 语义/缓存层 (旧版兼容，增加版本指纹)
        try:
            experience_manager.save_audit_experience(payload.tasks, payload.sql)
            if payload.user_input:
                current_fingerprint = {
                    "prompt_version": "2.0",
                    "schema_hash": "hsa_v2_core"
                }
                action_cache_manager.save(
                    payload.user_input, 
                    payload.sql, 
                    tasks=payload.tasks, 
                    methodology=payload.methodology, 
                    fingerprint=current_fingerprint
                )
        except Exception as e:
            logger.warning(f"兼容层保存失败: {e}")

        # 2. 企业级分层记忆层 (V3 Episodic Memory)
        try:
            from app.core.memory.manager import memory_hub
            episode_data = {
                "tasks": payload.tasks,
                "sql": payload.sql,
                "sql_history": payload.sql_history,
                "methodology": payload.methodology,
                "success": True,
                "timestamp": payload.audit_timestamp
            }
            await memory_hub.episodic.record_episode(payload.user_input, episode_data, importance=0.8)
            logger.success("✅ [Consolidator] 审计经验已成功沉淀至 Episodic Memory 层")
        except Exception as e:
            logger.warning(f"Episodic 记忆沉淀失败: {e}")

        return {}

# 单例导出
consolidator_agent = AuditConsolidatorAgent()
