"""
app/reflection_agent.py
=======================
[V150.0] 审计反思智能体 (Critic Agent)

负责：
1. 分析执行偏差：对比 SQL 执行结果（raw_data）与原始审计问题的差异。
2. 生成修复指令：当发生 Schema 错误或逻辑漂移时，给出具体的纠偏建议。
3. 逃生舱管理：当重试次数过多时，自动触发降级报告模式。
"""

from typing import Dict, Any, List, Optional
from loguru import logger
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from app.infra.model_manager import model_manager

class AuditReflectionAgent:
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries

    async def reflect(self, state: Dict[str, Any], config: Any) -> Dict[str, Any]:
        """执行自愈诊断逻辑"""
        retry = state.get("retry_count", 0)
        logger.warning(f"🕵️ [ReflectionAgent] 正在诊断执行偏差... (尝试 {retry}/{self.max_retries})")
        
        # 1. 准备模型角色
        from app.core.llm_provider import llm_provider
        role = "critic"
        
        # 2. 构造诊断消息上下文
        from app.prompts import CRITIC_PROMPT
        all_msgs = state.get("messages", [])
        
        # 提取原始问题（逻辑复用）
        original_q = self._extract_original_question(all_msgs) or "未获取到原始问题"
        original_q = original_q[:300]
        
        # 只取最近 2 条消息作为反思上下文，减少 Token 浪费
        critic_msgs = all_msgs[-2:] if len(all_msgs) > 2 else all_msgs
        
        messages = CRITIC_PROMPT.format_messages(
            original_question=original_q,
            methodology=state.get("methodology", "未定义协议"),
            raw_data=state.get("raw_data", "无数据")[:1000],
            error_log=state.get("error_log", "无报错日志"),
            messages=critic_msgs
        )

        # 3. 逃生舱逻辑 (Escape Hatch)
        if retry >= self.max_retries - 1:
            logger.warning(f"🛑 [ReflectionAgent] 达到上限，激活逃生舱。")
            feedback = (
                "⚠️ [系统提示：已进入降级报告模式]\n"
                "经过多次尝试，系统由于物理 Schema 缺失或逻辑冲突，无法生成完美的取证 SQL。\n"
                "请直接基于当前事实输出「受限核查报告」，并在报告中明确指出受限原因。"
            )
            response = AIMessage(content=feedback)
        else:
            response = await llm_provider.chat(
                role=role,
                messages=messages,
                config=config,
                state=state
            )
            feedback = str(response.content)
        
        logger.info(f"💡 [ReflectionAgent] 诊断建议: {feedback[:100]}...")
        
        return {
            "error_log": f"[CRITIC 反馈] {feedback}",
            "messages": [response]
        }

    def _extract_original_question(self, messages: List[BaseMessage]) -> Optional[str]:
        """从消息链中提取原始 HumanMessage 内容"""
        for msg in messages:
            if isinstance(msg, (HumanMessage, tuple)) or (hasattr(msg, "type") and msg.type in ("human", "user")):
                if isinstance(msg, tuple): return msg[1]
                return str(msg.content)
        return None

# 单例导出
reflection_agent = AuditReflectionAgent()
