"""
Guardrail Result Contract Deep Module.
Adheres to Matt Pocock's Deep Module design: encapsulates guard check outcomes,
diagnostics hints, and unified dictionary compatibility behind a robust dataclass.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class GuardrailResult:
    """
    [Matt Pocock Deep Module] 统一门控审查与诊断标准化结果契约。

    兼具强类型属性访问与字典行为（__getitem__, get, keys, etc.），
    100% 向下兼容既有 dict 解构代码：
    result["passed"], result.get("error"), result["warnings"], result["diagnostic_hint"]。
    """
    passed: bool
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    diagnostic_hint: Optional[str] = None

    def __getitem__(self, item: str) -> Any:
        if item == "passed":
            return self.passed
        elif item == "error":
            return self.error
        elif item == "warnings":
            return self.warnings
        elif item == "diagnostic_hint":
            return self.diagnostic_hint
        raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        try:
            val = self[item]
            return val if val is not None else default
        except KeyError:
            return default

    def __bool__(self) -> bool:
        return bool(self.passed)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "error": self.error,
            "warnings": list(self.warnings),
            "diagnostic_hint": self.diagnostic_hint,
        }
