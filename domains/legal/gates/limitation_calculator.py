from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class LimitationEvaluationResult(BaseModel):
    is_expired: bool
    years_elapsed: float
    effective_start_date: str
    interrupted_at: Optional[str] = None
    warning: Optional[str] = None
    is_peremptory: bool = False
    statutory_limit_years: float = 3.0
    law_ref: Optional[str] = None


_CAUSE_LIMITATIONS: Dict[str, Dict[str, Any]] = {
    "劳动争议纠纷": {
        "years": 1.0,
        "is_peremptory": False,
        "law_ref": "《中华人民共和国劳动争议调解仲裁法》第二十七条",
        "description": "劳动争议申请仲裁的时效期间为一年，从当事人知道或者应当知道其权利被侵害之日起计算；可因主张权利、申请调解发生时效中断。"
    },
    "建设工程施工合同纠纷": {
        "years": 1.5,
        "is_peremptory": True,
        "law_ref": "《最高人民法院关于审理建设工程施工合同纠纷案件适用法律若干问题的解释（一）》第四十一条",
        "description": "建设工程价款优先受偿权属于法定不变除斥期间，最长不得超过十八个月，自发包人应当给付工程款之日起算，不适用时效中断。"
    },
    "房屋租赁合同纠纷": {
        "years": 0.5,
        "is_peremptory": True,
        "law_ref": "《中华人民共和国民法典》第七百一十六条第二款",
        "description": "出租人知道或应当知道承租人转租但在六个月内未提出异议的视为同意，六个月异议期属于法定除斥期间，不可中断。"
    },
    "default": {
        "years": 3.0,
        "is_peremptory": False,
        "law_ref": "《中华人民共和国民法典》第一百八十八条、第一百九十五条",
        "description": "向人民法院请求保护民事权利的诉讼时效期间为三年，自权利人知道或者应当知道权利受到损害以及义务人之日起计算；提起诉讼或催告发生法定中断重新起算。"
    }
}


class LimitationCalculator:
    DATE_FORMAT = "%Y-%m-%d"
    LIMITATION_YEARS = 3.0

    def evaluate(
        self,
        due_date: str,
        demand_dates: List[str],
        filing_date: str,
        *,
        cause_of_action: str = "民间借贷纠纷",
    ) -> LimitationEvaluationResult:
        rule = _CAUSE_LIMITATIONS.get(cause_of_action, _CAUSE_LIMITATIONS["default"])
        limit_years = float(rule["years"])
        is_peremptory = bool(rule["is_peremptory"])
        law_ref = str(rule["law_ref"])

        t_due = datetime.strptime(due_date, self.DATE_FORMAT)
        t_filing = datetime.strptime(filing_date, self.DATE_FORMAT)

        sorted_demands = []
        for d_str in demand_dates:
            try:
                sorted_demands.append(datetime.strptime(d_str, self.DATE_FORMAT))
            except ValueError:
                continue
        sorted_demands.sort()

        effective_start = t_due
        interrupted_date_str = None

        if not is_peremptory:
            # 诉讼时效：催告在时效内可中断重新起算
            current_anchor = t_due
            for d in sorted_demands:
                diff_days = (d - current_anchor).days
                if 0 < diff_days <= (limit_years * 365.25):
                    current_anchor = d
                    effective_start = d
                    interrupted_date_str = d.strftime(self.DATE_FORMAT)

        final_diff_days = (t_filing - effective_start).days
        years_elapsed = round(final_diff_days / 365.25, 2)
        is_expired = years_elapsed > limit_years

        warning = None
        if is_expired:
            if is_peremptory:
                warning = (
                    f"自 {effective_start.strftime(self.DATE_FORMAT)} 起算至主张日已跨越 {years_elapsed} 年，"
                    f"超过{law_ref}规定之 {limit_years} 年法定除斥期间。除斥期间为不变期间，不适用中断规定，实体权利已消灭。"
                )
            else:
                warning = (
                    f"自 {effective_start.strftime(self.DATE_FORMAT)} 起算至起诉日已跨越 {years_elapsed} 年，"
                    f"超过{law_ref}规定之 {limit_years} 年诉讼时效，诉讼时效已届满，存在严重败诉风险。"
                )

        return LimitationEvaluationResult(
            is_expired=is_expired,
            years_elapsed=years_elapsed,
            effective_start_date=effective_start.strftime(self.DATE_FORMAT),
            interrupted_at=interrupted_date_str,
            warning=warning,
            is_peremptory=is_peremptory,
            statutory_limit_years=limit_years,
            law_ref=law_ref,
        )
