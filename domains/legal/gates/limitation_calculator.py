from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

class LimitationEvaluationResult(BaseModel):
    is_expired: bool
    years_elapsed: float
    effective_start_date: str
    interrupted_at: Optional[str] = None
    warning: Optional[str] = None

class LimitationCalculator:
    DATE_FORMAT = "%Y-%m-%d"
    LIMITATION_YEARS = 3.0

    def evaluate(
        self,
        due_date: str,
        demand_dates: List[str],
        filing_date: str
    ) -> LimitationEvaluationResult:
        t_due = datetime.strptime(due_date, self.DATE_FORMAT)
        t_filing = datetime.strptime(filing_date, self.DATE_FORMAT)

        sorted_demands = []
        for d_str in demand_dates:
            try:
                sorted_demands.append(datetime.strptime(d_str, self.DATE_FORMAT))
            except ValueError:
                continue
        sorted_demands.sort()

        # 计算时效起算点：如果有催收事件，且发生在时效期间内，重新起算
        effective_start = t_due
        interrupted_date_str = None

        current_anchor = t_due
        for d in sorted_demands:
            diff_days = (d - current_anchor).days
            if 0 < diff_days <= (self.LIMITATION_YEARS * 365.25):
                current_anchor = d
                effective_start = d
                interrupted_date_str = d.strftime(self.DATE_FORMAT)

        final_diff_days = (t_filing - effective_start).days
        years_elapsed = round(final_diff_days / 365.25, 2)
        is_expired = years_elapsed > self.LIMITATION_YEARS

        warning = None
        if is_expired:
            warning = f"自 {effective_start.strftime(self.DATE_FORMAT)} 起算至起诉日已跨越 {years_elapsed} 年，超过民法典规定之3年普通诉讼时效，诉讼时效已届满，存在严重败诉风险。"

        return LimitationEvaluationResult(
            is_expired=is_expired,
            years_elapsed=years_elapsed,
            effective_start_date=effective_start.strftime(self.DATE_FORMAT),
            interrupted_at=interrupted_date_str,
            warning=warning
        )
