"""
app/agents/reflection_agent.py
==============================
[V150.0 / SPEC-227 / Matt Pocock Deep Module] 审计反思智能体 (Critic Agent)

负责：
1. 分析执行偏差：对比 SQL 执行结果（raw_data）与原始审计问题的差异。
2. 生成修复指令：当发生 Schema 错误或逻辑漂移时，给出具体的纠偏建议。
3. 逃生舱管理：当重试次数过多时，自动触发降级报告模式。
"""

from __future__ import annotations
from typing import Any, Dict, Optional
from loguru import logger
from langchain_core.messages import AIMessage
from app.agents.reflection_diagnostic_policy import ReflectionDiagnosticPolicy
from app.agents.reflection_prompt_assembler import ReflectionPromptAssembler


class AuditReflectionAgent:
    """审计反思智能体门面：聚合反思策略与上下文装配器，执行大模型自纠偏诊断。"""

    def __init__(
        self,
        max_retries: int = 3,
        diagnostic_policy: Optional[ReflectionDiagnosticPolicy] = None,
        prompt_assembler: Optional[ReflectionPromptAssembler] = None,
    ):
        self.max_retries = max_retries
        self.policy = diagnostic_policy or ReflectionDiagnosticPolicy(max_retries=max_retries)
        self.assembler = prompt_assembler or ReflectionPromptAssembler()

    async def reflect(self, state: Dict[str, Any], config: Any) -> Dict[str, Any]:
        """执行自愈诊断逻辑"""
        retry = state.get("retry_count", 0)
        logger.warning(f"🕵️ [ReflectionAgent] 正在诊断执行偏差... (尝试 {retry}/{self.max_retries})")

        # 1. 逃生舱熔断逻辑 (Escape Hatch)
        if self.policy.is_escape_hatch_triggered(retry):
            response = self.policy.generate_escape_hatch_message()
            feedback = str(response.content)
        else:
            # 2. 准备模型角色与上下文
            from app.core.llm_provider import llm_provider

            role = "critic"
            messages = self.assembler.assemble_critic_messages(state)

            response = await llm_provider.chat(
                role=role,
                messages=messages,
                config=config,
                state=state,
            )
            feedback = str(response.content)

        logger.info(f"💡 [ReflectionAgent] 诊断建议: {feedback[:100]}...")

        return {
            "error_log": f"[CRITIC 反馈] {feedback}",
            "messages": [response],
            "retry_count": retry + 1,
        }


# 单例导出（保持外部引用向后兼容）
reflection_agent = AuditReflectionAgent()
