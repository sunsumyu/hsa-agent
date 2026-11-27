from typing import List, Optional
from pydantic import BaseModel

class EstoppelEvaluationResult(BaseModel):
    has_contradiction: bool
    conflict_type: Optional[str] = None
    explanation: Optional[str] = None

class EstoppelDetector:
    def evaluate(self, claims: List[str]) -> EstoppelEvaluationResult:
        full_text = " ".join(claims)
        
        claims_void = any(k in full_text for k in ["合同无效", "协议无效", "确认无效", "无效合同"])
        claims_damages = any(k in full_text for k in ["违约金", "合同违约赔偿", "约定违约金"])

        if claims_void and claims_damages:
            return EstoppelEvaluationResult(
                has_contradiction=True,
                conflict_type="合同无效与违约金互斥",
                explanation="违约金条款依附于合同有效生效。主张合同无效时，无法基于有效合同之约定主张违约金责任，应调整为缔约过失责任或返还财产及资金占用费。"
            )

        return EstoppelEvaluationResult(has_contradiction=False)
