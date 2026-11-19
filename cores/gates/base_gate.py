from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class GateResult(BaseModel):
    passed: bool
    reason: Optional[str] = None
    error_code: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)

class BaseSymbolicGate(ABC):
    @abstractmethod
    def evaluate(self, state: Dict[str, Any]) -> GateResult:
        """Evaluate the current state deterministically against domain invariants."""
        pass
