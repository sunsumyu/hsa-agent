from pydantic import BaseModel
from typing import Optional

class UsuryEvaluationResult(BaseModel):
    is_usurious: bool
    contract_rate: float
    ceiling_rate: float
    enforceable_rate: float
    excess_rate: float
    clamping_notice: Optional[str] = None

class UsuryEvaluator:
    CEILING_MULTIPLIER = 4.0

    def evaluate(
        self,
        contract_rate: float,
        lpr_benchmark: float,
        principal: float
    ) -> UsuryEvaluationResult:
        ceiling_rate = round(lpr_benchmark * self.CEILING_MULTIPLIER, 4)
        is_usurious = contract_rate > ceiling_rate

        if is_usurious:
            enforceable_rate = ceiling_rate
            excess_rate = round(contract_rate - ceiling_rate, 4)
            notice = (
                f"约定年利率 {contract_rate * 100:.1f}% 超过司法解释上限 {ceiling_rate * 100:.1f}% "
                f"(起诉时一年期LPR {lpr_benchmark * 100:.2f}% 的4倍)。"
                f"超出部分年利率 {excess_rate * 100:.2f}% 法院不予支持。"
            )
        else:
            enforceable_rate = contract_rate
            excess_rate = 0.0
            notice = None

        return UsuryEvaluationResult(
            is_usurious=is_usurious,
            contract_rate=contract_rate,
            ceiling_rate=ceiling_rate,
            enforceable_rate=enforceable_rate,
            excess_rate=excess_rate,
            clamping_notice=notice
        )
