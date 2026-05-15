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

    def consolidate(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """对执行成功的路径进行固化"""
        tasks = state.get("tasks", [])
        sql = state.get("sql_query", "")
        methodology = state.get("methodology", "")
        
        # 提取用户输入
        metadata = state.get("metadata") or {}
        user_input = metadata.get("user_question")
        
        if not user_input:
            # 兜底消息链提取
            from langchain_core.messages import HumanMessage
            for msg in state.get("messages", []):
                if isinstance(msg, (HumanMessage, tuple)) or (hasattr(msg, "type") and msg.type in ("human", "user")):
                    user_input = msg[1] if isinstance(msg, tuple) else str(msg.content)
                    break

        if tasks and sql:
            # 验证门控：只有无报错且有数据的 SQL 才值得学习
            has_error = bool(state.get("error_log"))
            raw_data = state.get("raw_data", "")
            has_data = bool(raw_data.strip()) and "查询失败" not in str(raw_data)

            if has_error or not has_data:
                logger.warning(f"🚫 [Consolidator] SQL 未通过验证，跳过学习 (error={has_error}, data={has_data})")
            else:
                # 1. 语义级经验固化
                experience_manager.save_audit_experience(tasks, sql)
                # 2. 精准动作链缓存 (V159.0)
                if user_input:
                    action_cache_manager.save(user_input, sql, tasks=tasks, methodology=methodology)
                    logger.success(f"✅ [Consolidator] 审计动作链已固化至语义层与缓存层")
        
        return {}

# 单例导出
consolidator_agent = AuditConsolidatorAgent()
