"""
Field Alias Catalog Deep Module.
Adheres to Matt Pocock's Deep Module design: encapsulates healthcare insurance
physical schema aliases, forbidden column anti-hallucination lists, and canonical
resolution indexes behind a clean interface.
"""
from typing import List, Dict, Any, Optional, Set
from loguru import logger

FIELD_ALIAS_REGISTRY: List[Dict[str, Any]] = [
    {
        "canonical": "fixmedins_code",
        "aliases": ["医疗机构编码", "机构代码", "机构编号", "机构", "定点机构代码", "定点机构编码", "定点机构编号", "hospital_id", "hosp_id", "inst_code"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "医疗机构唯一编码（必须使用此字段，严禁使用 hosp_code）",
        "forbidden_aliases": ["hosp_code"],
    },
    {
        "canonical": "fixmedins_name",
        "aliases": ["医院名称", "机构名称", "hosp_name", "hospital_name", "provider_name", "med_inst_name"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "医疗机构名称",
        "forbidden_aliases": ["hosp_name"],
    },
    {
        "canonical": "psn_no",
        "aliases": ["patient_id", "person_id", "psn_id", "insured_no", "psn_no", "patient_no"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "参保人唯一标识",
        "forbidden_aliases": [],
    },
    {
        "canonical": "gend",
        "aliases": ["性别代码"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "性别代码：1=男，2=女",
        "forbidden_aliases": ["gender", "sex"],
    },
    {
        "canonical": "dise_name",
        "aliases": ["diagnosis", "disease_name", "diag_name", "diagnosis_code", "diag_code", "dise_code"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "主要诊断名称",
        "forbidden_aliases": ["diagnosis", "disease_name"],
    },
    {
        "canonical": "start_date",
        "aliases": ["adm_date", "admit_date", "in_date", "admission_date", "start_time"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "住院开始日期。⚠️注意：若在 GROUP BY 中使用了 toStartOfDay() 等函数处理此字段，SELECT 中也必须使用相同的函数，严禁选原始字段。",
        "forbidden_aliases": ["adm_date", "admit_date"],
    },
    {
        "canonical": "end_date",
        "aliases": ["dis_date", "discharge_date", "out_date", "finish_date"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "住院结束日期。⚠️注意：若在 GROUP BY 中使用了 toStartOfDay() 等函数处理此字段，SELECT 中也必须使用相同的函数，严禁选原始字段。",
        "forbidden_aliases": ["dis_date", "discharge_date"],
    },
    {
        "canonical": "medfee_sumamt",
        "aliases": ["医疗总费用", "结算金额", "total_fee", "total_amount", "medfee", "total_expense", "total_bill", "gross_amount", "medical_cost", "fee_amt", "pay_amount", "fee_amount"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "医疗总费用（必须使用此字段，严禁使用 total_fee 或 amount 或 fee_amt）",
        "forbidden_aliases": ["total_fee", "total_amount", "amount", "fee_amt", "pay_amount"],
    },
    {
        "canonical": "fund_pay_sumamt",
        "aliases": ["insurance_pay", "medical_pay", "fund_pay", "reimbursement_amount", "fund_amt", "reimbursement", "benefit_amount", "covered_amount"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "医保基金实际支付金额",
        "forbidden_aliases": ["insurance_pay", "medical_pay"],
    },
    {
        "canonical": "setl_time",
        "aliases": ["settle_time", "settlement_date", "setl_time"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "医疗费用结算时间。⚠️注意：若在 GROUP BY 中使用了 toStartOfDay() 等函数处理此字段，SELECT 中也必须使用相同的函数，严禁选原始字段。",
        "forbidden_aliases": ["settle_time"],
    },
    {
        "canonical": "setl_id",
        "aliases": ["settlement_id", "settle_id", "bill_id", "record_id", "admission_id"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "结算流水唯一标识",
        "forbidden_aliases": ["settlement_id"],
    },
    {
        "canonical": "med_type",
        "aliases": ["medical_type", "visit_type", "med_type", "medical_category", "treatment_type", "admission_type", "visit_category", "treat_type"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "就医类型（门诊/住院/药店）",
        "forbidden_aliases": ["medical_type", "medical_category"],
    },
    {
        "canonical": "hilist_name",
        "aliases": ["item_name", "drug_name", "treat_name", "project_name", "fee_name", "hilist_name", "det_item_name"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "费用明细项目名称（药品/诊疗/耗材）",
        "forbidden_aliases": ["drug_name", "treat_name", "item_name", "det_item_name"],
    },
    {
        "canonical": "hilist_code",
        "aliases": ["item_code", "drug_code", "treat_code", "list_code", "hilist_code", "service_code", "project_code", "fee_code", "item_id"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "医保标准项目编码",
        "forbidden_aliases": ["drug_code", "item_code"],
    },
    {
        "canonical": "det_item_fee_sumamt",
        "aliases": ["item_fee", "detail_amount", "item_amount", "det_item_fee_sumamt"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "明细项目总金额",
        "forbidden_aliases": ["item_fee", "item_amount"],
    },
    {
        "canonical": "tel",
        "aliases": ["手机号", "电话", "联系方式", "mobile", "phone", "tel"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "参保人联系电话（提示：结算明细表中该字段可能为空，建议优先调用 query_fraud_ring 查图）",
        "forbidden_aliases": [],
    },
    {
        "canonical": "mon",
        "aliases": ["stats_period", "stat_period", "period", "stats_month", "stat_month", "统计周期", "统计月份", "费用月份", "月份", "mon"],
        "table": "fqz_cgzhan_hosp_fee",
        "desc": "统计月份/周期 (YYYYMM)",
        "forbidden_aliases": [],
    },
    {
        "canonical": "__COMPUTED__",
        "aliases": [],
        "table": "__VIRTUAL__",
        "desc": "以下字段是常见幻觉字段，物理不存在，必须通过 SQL 公式计算",
        "forbidden_aliases": [
            "vix", "variation_index", "变异指数",
            "overlap_hours", "overlap_days",
            "department_id", "dept_id", "dept_code",
            "visit_count", "admission_count",
            "age", "patient_age",
            "readmission_flag", "is_readmission",
            "los", "length_of_stay",
        ],
    },
]


class FieldAliasCatalog:
    """字段别名编目与正规化映射深模块"""

    def __init__(self, registry: Optional[List[Dict[str, Any]]] = None):
        self._registry = registry or FIELD_ALIAS_REGISTRY
        self._alias_map: Dict[str, str] = {}
        self._forbidden_map: Dict[str, str] = {}
        self._forbidden_set: Set[str] = set()

        for entry in self._registry:
            canonical = entry["canonical"].strip()
            for alias in entry.get("aliases", []):
                self._alias_map[alias.strip().lower()] = canonical
            for forbidden in entry.get("forbidden_aliases", []):
                fb = forbidden.strip().lower()
                self._forbidden_set.add(fb)
                if canonical != "__COMPUTED__":
                    self._forbidden_map[fb] = canonical

    @property
    def registry(self) -> List[Dict[str, Any]]:
        return self._registry

    @property
    def alias_map(self) -> Dict[str, str]:
        return self._alias_map

    @property
    def forbidden_map(self) -> Dict[str, str]:
        return self._forbidden_map

    @property
    def forbidden_set(self) -> Set[str]:
        return self._forbidden_set

    def resolve(self, field_name: str) -> Optional[str]:
        """将别名解析为正规字段名"""
        if not field_name:
            return None
        fn = field_name.lower().strip()
        if fn in self._alias_map:
            canonical = self._alias_map[fn]
            logger.debug(f"[FieldKG] 别名解析: {field_name} -> {canonical}")
            return canonical
        if fn in self._forbidden_map:
            canonical = self._forbidden_map[fn]
            logger.debug(f"[FieldKG] 禁用别名纠错解析: {field_name} -> {canonical}")
            return canonical
        for entry in self._registry:
            if entry["canonical"].lower() == fn:
                return entry["canonical"]
        return None

    def is_forbidden(self, field_name: str) -> bool:
        """判断一个字段名是否是已知的错误/不存在字段"""
        if not field_name:
            return False
        return field_name.lower().strip() in self._forbidden_set
