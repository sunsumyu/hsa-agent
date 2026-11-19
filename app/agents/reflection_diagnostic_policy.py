"""
[SPEC-227 / Matt Pocock Deep Module] 审计反思诊断策略深模块 (Diagnostic Policy)

专职封装反思重试判定、逃生舱降级与受限模式仲裁逻辑。
"""

from __future__ import annotations
from typing import Optional
from langchain_core.messages import AIMessage
from loguru import logger


class ReflectionDiagnosticPolicy:
    """反思与诊断策略深模块：专职封装逃生舱熔断与受限报告生成规则。"""

    DEFAULT_ESCAPE_HATCH_PROMPT = (
        "⚠️ [系统提示：已进入降级报告模式]\n"
        "经过多次尝试，系统由于物理 Schema 缺失或逻辑冲突，无法生成完美的取证 SQL。\n"
        "请直接基于当前事实输出「受限核查报告」，并在报告中明确指出受限原因。"
    )

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries

    def is_escape_hatch_triggered(self, retry_count: int) -> bool:
        """当重试次数达到上限前一轮或已超上限时，触发逃生舱"""
        return retry_count >= self.max_retries - 1

    def generate_escape_hatch_message(self, custom_prompt: Optional[str] = None) -> AIMessage:
        """生成标准逃生舱提示消息"""
        content = custom_prompt or self.DEFAULT_ESCAPE_HATCH_PROMPT
        logger.warning("🛑 [DiagnosticPolicy] 达到重试上限，激活逃生舱降级机制。")
        return AIMessage(content=content)
