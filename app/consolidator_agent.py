"""
app/consolidator_agent.py
=========================
[V150.0] 审计固化智能体 (Consolidator Agent)

负责：
1. 经验固化：将执行成功的审计路径（Task + SQL）保存至 FAISS 经验库。
2. 精准缓存：将用户原始问题与验证通过的 SQL 绑定，实现秒级二次命中。
"""

from typing import Dict, Any, List
from loguru import logger
from app.experience import experience_manager
from app.semantic_memory import action_cache_manager

class AuditConsolidatorAgent:
    def __init__(self):
        pass

    async def consolidate(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """对执行成功的路径进行多级固化 [V178.9]"""
        tasks = state.get("tasks", [])
        sql = state.get("sql_query", "")
        sql_history = state.get("sql_history", [])
        methodology = state.get("methodology", "")
        
        # 1. 提取用户输入
        metadata = state.get("metadata") or {}
        user_input = metadata.get("user_question")
        
        if not user_input:
            from langchain_core.messages import HumanMessage
            for msg in state.get("messages", []):
                if isinstance(msg, (HumanMessage, tuple)) or (hasattr(msg, "type") and msg.type in ("human", "user")):
                    user_input = msg[1] if isinstance(msg, tuple) else str(msg.content)
                    break

        if tasks and (sql or sql_history):
            # 2. 验证门控：只有无报错且有数据的 SQL 才值得学习
            has_error = bool(state.get("error_log"))
            raw_data = state.get("raw_data", "")
            has_data = bool(raw_data.strip()) and "查询失败" not in str(raw_data)

            if has_error or not has_data:
                logger.warning(f"🚫 [Consolidator] 审计逻辑未闭环或无数据，跳过经验沉淀")
                return {}

            logger.info(f"✨ [Consolidator] 正在为问题「{user_input[:15]}...」执行经验沉淀...")

            # 3. 语义/缓存层 (旧版兼容)
            try:
                experience_manager.save_audit_experience(tasks, sql)
                if user_input:
                    action_cache_manager.save(user_input, sql, tasks=tasks, methodology=methodology)
            except Exception as e:
                logger.warning(f"兼容层保存失败: {e}")

            # 4. 企业级分层记忆层 (V3 Episodic Memory)
            from app.core.memory.manager import memory_hub
            episode_data = {
                "tasks": tasks,
                "sql": sql,
                "sql_history": sql_history,
                "methodology": methodology,
                "success": True,
                "timestamp": metadata.get("audit_timestamp")
            }
            await memory_hub.episodic.record_episode(user_input, episode_data, importance=0.8)
            
            logger.success(f"✅ [Consolidator] 审计经验已成功沉淀至 Episodic Memory 层")
        
        return {}

# 单例导出
consolidator_agent = AuditConsolidatorAgent()
