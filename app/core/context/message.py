"""
app/core/message.py
===================
[V152.0] 工业级审计消息协议 (AuditMessage Protocol)

实现“对内丰富，对外兼容”原则：
1. 对内：携带全链路 TraceID、耗时、模型指纹、Token 成本等元数据。
2. 对外：支持一键转换为 OpenAI/LangChain 标准格式。
"""

from typing import Optional, Dict, Any, List, Literal
from datetime import datetime
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage

MessageRole = Literal["user", "assistant", "system", "tool", "thought"]

class AuditMessage(BaseModel):
    """
    审计消息类：封装标准消息及其审计元数据。
    """
    role: MessageRole
    content: str
    
    # --- 审计元数据 (Audit Metadata) ---
    trace_id: str = Field(default="", description="全链路请求 ID")
    node_name: str = Field(default="", description="生成该消息的 Agent 节点名")
    model_id: str = Field(default="unknown", description="实际执行物理模型 ID")
    latency_ms: Optional[float] = Field(default=None, description="模型响应耗时(毫秒)")
    token_usage: Dict[str, int] = Field(default_factory=lambda: {"input": 0, "output": 0}, description="Token 消耗详情")
    timestamp: datetime = Field(default_factory=datetime.now, description="消息产生时间")
    
    # --- 扩展元数据 ---
    additional_kwargs: Dict[str, Any] = Field(default_factory=dict, description="其他扩展参数")

    @classmethod
    def from_langchain(cls, msg: BaseMessage, **metadata) -> "AuditMessage":
        """从 LangChain 消息对象转换"""
        role_map = {
            "human": "user",
            "ai": "assistant",
            "system": "system",
            "tool": "tool"
        }
        role = role_map.get(msg.type, "user")
        
        # 提取 LangChain 内置元数据
        usage = getattr(msg, "usage_metadata", {}) or {}
        in_t = usage.get("input_tokens", 0)
        out_t = usage.get("output_tokens", 0)
        
        return cls(
            role=role,
            content=str(msg.content),
            token_usage={"input": in_t, "output": out_t},
            additional_kwargs=getattr(msg, "additional_kwargs", {}),
            **metadata
        )

    def to_langchain(self) -> BaseMessage:
        """转换为 LangChain 消息对象"""
        if self.role == "user":
            return HumanMessage(content=self.content, additional_kwargs=self.additional_kwargs)
        elif self.role == "assistant":
            return AIMessage(
                content=self.content, 
                additional_kwargs=self.additional_kwargs,
                usage_metadata={"input_tokens": self.token_usage["input"], "output_tokens": self.token_usage["output"]}
            )
        elif self.role == "system":
            return SystemMessage(content=self.content, additional_kwargs=self.additional_kwargs)
        elif self.role == "tool":
            return ToolMessage(
                content=self.content, 
                tool_call_id=self.additional_kwargs.get("tool_call_id", ""),
                additional_kwargs=self.additional_kwargs
            )
        return HumanMessage(content=self.content)

    def to_openai_dict(self) -> Dict[str, Any]:
        """转换为 OpenAI API 兼容字典格式"""
        return {
            "role": "assistant" if self.role == "thought" else self.role,
            "content": self.content
        }

    def __str__(self) -> str:
        time_str = self.timestamp.strftime("%H:%M:%S")
        safe_role = str(self.role or "unknown").upper()
        return f"[{time_str}] [{safe_role}] {self.content[:100]}..."
