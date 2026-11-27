from typing import TypedDict, List, Dict, Any, Optional
from langchain_core.messages import BaseMessage

class BaseCognitiveState(TypedDict):
    thread_id: str
    messages: List[BaseMessage]
    metadata: Dict[str, Any]
    current_step: str
    error_log: Optional[str]
    retry_count: int
    is_awaiting_human: bool
