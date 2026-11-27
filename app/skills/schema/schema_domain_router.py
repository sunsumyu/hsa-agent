"""
app/skills/schema_domain_router.py
==================================
[Deep Module] 医保 Schema 数据域路由与跨域概念本体解析引擎

遵循 Matt Pocock 的 Deep Module 设计原则 (Narrow Interface, Deep Implementation):
- 窄接口:
    - classify_question_domains(user_question)
    - semantic_classify_domains(user_question)
    - get_ontology_hints(user_question)
    - resolve_target_tables(user_question)
- 深实现:
    - 封装四大医保数据域定义与敏感关键词库
    - 封装空间/时序/行政区划跨域概念本体映射 (Ontology Hinting)
    - 封装 BM25 + Ontology + Embedding 多通道混合召回与打分融合
    - 封装异常降级与兜底表路由策略
"""

from __future__ import annotations
from typing import List, Dict, Optional, Tuple, Set
from loguru import logger


# ── 数据域定义：问题分类 & 表路由映射 ──────────────────────────────────────────
DATA_DOMAINS: List[Dict] = [
    {
        "domain": "settlement",
        "desc": "结算/住院/门诊/报销/患者个人明细",
        "tables": ["FQZ_GZ_JZSJ_ALL_QL"],
        "keywords": [
            "结算", "住院", "门诊", "报销", "费用", "金额", "患者", "参保",
            "重复", "分解", "挂床", "冒名", "套保", "骗保",
            "性别", "诊断", "手术", "科室", "天数", "床位",
            "setl", "psn", "mdtrt", "medfee", "fund_pay",
            "入院", "出院", "再入院", "短期", "转院",
            "异常", "审计", "稽核", "核查", "违规",
            "P99", "psn_no",
        ],
    },
    {
        "domain": "hospital_monthly",
        "desc": "医疗机构月度汇总统计",
        "tables": ["FQZ_ALL_YY_YD_1"],
        "keywords": [
            "医院", "机构", "月度", "汇总", "统计", "排名",
            "变异", "VIX", "离群", "偏高", "偏低",
            "医院对比", "机构对比", "总额",
            "fixmedins",
        ],
    },
    {
        "domain": "drug_catalog",
        "desc": "药品/诊疗项目/耗材目录",
        "tables": ["FQZ_DRUG_MCS_INFO_LIST"],
        "keywords": [
            "药品", "药物", "处方", "用药", "购药",
            "目录", "耗材", "诊疗项目", "医保目录",
            "drug", "med_list", "hilist",
        ],
    },
    {
        "domain": "outpatient_detail",
        "desc": "门诊费用明细/乡镇卫生院/村卫生室",
        "tables": ["FQZ_FYMX_TEST"],
        "keywords": [
            "乡镇卫生院", "村卫生室", "门诊统筹", "批量刷单",
            "连续刷卡", "门诊费用", "牙", "拔牙", "口腔",
            "理疗", "康复", "卫生室", "卫生院", "门诊明细",
            "刷单", "fymx",
        ],
    },
]

# ── 跨域概念本体映射 ──────────────────────────────────────────────────────────
CROSS_DOMAIN_ONTOLOGY: Dict[str, Dict] = {
    "空间": {"domains": ["settlement", "hospital_monthly"], "hint": "空间距离需通过 admdvs 行政区划编码评估，严禁使用 latitude/longitude"},
    "距离": {"domains": ["settlement", "hospital_monthly"], "hint": "物理距离通过 substring(admdvs,1,4) 判断跨市就医"},
    "跨市": {"domains": ["settlement", "hospital_monthly"], "hint": "跨市就医: substring(admdvs,1,4) != substring(other_admdvs,1,4)"},
    "跨地区": {"domains": ["settlement", "hospital_monthly"], "hint": "跨地区就医判定同跨市"},
    "行政区划": {"domains": ["settlement", "hospital_monthly"], "hint": "admdvs 字段存储行政区划编码"},
    "时序碰撞": {"domains": ["settlement"], "hint": "同一患者短时间内跨机构就诊，需用 setl_time + psn_no 排序"},
    "空间时序": {"domains": ["settlement"], "hint": "空间+时序交叉对碰：admdvs跨市 + setl_time时间窗口"},
    "重叠住院": {"domains": ["settlement"], "hint": "住院时间重叠需比较 start_date/end_date"},
}

DEFAULT_TABLES: List[str] = ["FQZ_GZ_JZSJ_ALL_QL"]


def classify_question_domains(user_question: str) -> List[Dict]:
    """
    根据用户问题关键词统计快速识别涉及的数据域。
    Returns:
        匹配的域列表，按相关度降序，每项含 domain/desc/tables/score
    """
    if not user_question or not user_question.strip():
        return [DATA_DOMAINS[0]]

    text = user_question.lower()
    scored = []
    for domain in DATA_DOMAINS:
        score = sum(1 for kw in domain["keywords"] if kw.lower() in text)
        if score > 0:
            scored.append({**domain, "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)

    if not scored:
        return [DATA_DOMAINS[0]]

    return scored


def semantic_classify_domains(user_question: str) -> List[Dict]:
    """
    BM25 + 跨域概念本体 + Embedding 多通道混合召回与打分融合。
    """
    if not user_question or not user_question.strip():
        return [DATA_DOMAINS[0]]

    text = user_question.lower()

    # 1. 词频通道 (BM25 启发式)
    bm25_scores = []
    for domain in DATA_DOMAINS:
        score = sum(1 for kw in domain["keywords"] if kw.lower() in text)
        if score > 0:
            bm25_scores.append({**domain, "score": score, "hint": ""})

    # 2. 跨域概念本体通道
    ontology_scores = []
    for concept, mapping in CROSS_DOMAIN_ONTOLOGY.items():
        if concept.lower() in text:
            for domain_name in mapping.get("domains", []):
                domain_def = next((d for d in DATA_DOMAINS if d["domain"] == domain_name), None)
                if domain_def:
                    ontology_scores.append({**domain_def, "score": 5, "hint": mapping.get("hint", "")})

    # 3. 语义向量通道 (Embedding，尽力而为容错)
    embedding_scores = []
    try:
        from app.core.memory.semantic_memory import cognitive_memory_manager
        if cognitive_memory_manager.semantic:
            docs = cognitive_memory_manager.semantic.recall_expert_knowledge(user_question, top_k=3)
            for doc in docs:
                content = doc.page_content.lower()
                for domain in DATA_DOMAINS:
                    domain_kw_match = sum(1 for kw in domain["keywords"][:5] if kw.lower() in content)
                    if domain_kw_match > 0:
                        embedding_scores.append({**domain, "score": 2, "hint": f"语义关联: {doc.page_content[:50]}..."})
    except Exception as e:
        logger.debug(f"[SchemaDomainRouter] Embedding recall skipped: {e}")

    # 4. 多通道打分融合
    all_scores: Dict[str, Dict] = {}
    for item in bm25_scores:
        key = item["domain"]
        if key not in all_scores:
            all_scores[key] = item
        else:
            all_scores[key]["score"] += item["score"]

    for item in ontology_scores:
        key = item["domain"]
        if key not in all_scores:
            all_scores[key] = item
        else:
            all_scores[key]["score"] += item["score"]
            if item["hint"] and not all_scores[key].get("hint"):
                all_scores[key]["hint"] = item["hint"]

    for item in embedding_scores:
        key = item["domain"]
        if key not in all_scores:
            all_scores[key] = item
        else:
            all_scores[key]["score"] += item["score"]

    scored = sorted(all_scores.values(), key=lambda x: x["score"], reverse=True)
    if not scored:
        return [DATA_DOMAINS[0]]

    logger.info(f"[SchemaDomainRouter] semantic_classify: {len(scored)} domains, top={scored[0]['domain']} score={scored[0]['score']}")
    return scored


def get_ontology_hints(user_question: str) -> Optional[str]:
    """提取跨域本体映射提示文本"""
    if not user_question:
        return None
    text = user_question.lower()
    hints = []
    for concept, mapping in CROSS_DOMAIN_ONTOLOGY.items():
        if concept.lower() in text:
            hint = mapping.get("hint", "")
            if hint:
                hints.append(f"【{concept}】{hint}")
    if hints:
        return "\n".join(hints)
    return None


def resolve_target_tables(user_question: str) -> List[str]:
    """返回目标物理表名列表（保序、去重、具备兜底）"""
    domains = semantic_classify_domains(user_question)
    tables: List[str] = []
    seen: Set[str] = set()
    for d in domains:
        for t in d.get("tables", []):
            if t not in seen:
                tables.append(t)
                seen.add(t)
    return tables if tables else list(DEFAULT_TABLES)
