"""
Medical Intent Lexicon Deep Module.
Adheres to Matt Pocock's Deep Module design: encapsulates clinical intent
expansion vocabulary, specialized keyword mappings, and deterministic term extraction.
"""
from typing import Dict, List

MEDICAL_KNOWLEDGE_MAP: Dict[str, List[str]] = {
    "妇科": ["妇科门诊", "妇科病房", "阴道镜检查", "宫颈刮片", "附件切除", "子宫肌瘤", "产科关联项"],
    "产科": ["产科门诊", "分娩", "剖宫产", "顺产", "围产期核查", "妇科关联项"],
    "妇产科": ["妇科", "产科", "计划生育科", "生殖医学"],
    "男性": ["前列腺", "阴囊", "睾丸", "输精管"],
    "女性": ["子宫", "卵巢", "输卵管", "阴道", "乳腺", "妇科", "产科"],
    "分解住院": ["多单结算", "24小时再次入院", "相同主诊断重复入院"],
    "异地就医": ["跨省就医", "省内异地", "备案核查"],
    "虚假住院": ["挂床住院", "日间手术转住院", "空床核查"],
}


def expand_medical_intent(text: str) -> List[str]:
    """根据关键词自动扩展医学意图 [V180.0]"""
    if not text:
        return []
    expansions = []
    for key, related in MEDICAL_KNOWLEDGE_MAP.items():
        if key in text:
            expansions.extend(related)
    return list(set(expansions))
