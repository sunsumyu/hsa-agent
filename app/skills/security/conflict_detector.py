"""
[V4.9.6] MemPalace 记忆冲突检测器 (Conflict Detector)

分析 Agent 的发现线索 (Findings) 中是否存在事实冲突或前后矛盾。
"""
import re
import hashlib
import threading
from typing import Any, Dict, List, Tuple

# [V179.3] 使用 SHA-256 替代 MD5
def get_finding_hash(finding: str) -> str:
    return hashlib.sha256(finding.strip().encode('utf-8')).hexdigest()

# [V179.6] 线程安全的冲突决策存储
class ResolvedFindingsStore:
    """线程安全的冲突决策存储，替代全局字典"""
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._data: Dict[str, bool] = {}
        return cls._instance
    
    def set(self, finding_hash: str, accepted: bool):
        with self._lock:
            self._data[finding_hash] = accepted
    
    def get(self, finding_hash: str) -> bool:
        with self._lock:
            return self._data.get(finding_hash)
    
    def exists(self, finding_hash: str) -> bool:
        with self._lock:
            return finding_hash in self._data

_findings_store = ResolvedFindingsStore()

def mark_resolved(finding: str, accepted: bool):
    """记录人类审计员关于某项证据是否保留的决策"""
    _findings_store.set(get_finding_hash(finding), accepted)

def is_discarded(finding: str) -> bool:
    """该条目是否被标记为废弃"""
    return _findings_store.get(get_finding_hash(finding)) is False

def _detect_amount_conflicts(valid_findings: List[str]) -> List[Dict[str, Any]]:
    conflicts: List[Dict[str, Any]] = []
    entity_money_map: Dict[str, List[Tuple[str, str]]] = {}
    for f in valid_findings:
        hosp_match = re.search(r"([\u4e00-\u9fff]{2,10}(?:医院|门诊|诊所))", f)
        money_match = re.search(r"(?:金额|违规金额|涉案金额|涉及.*?金额).*?([\d,，\.]+)\s*(?:元|万元)", f)
        if not (hosp_match and money_match):
            continue
        hosp, money = hosp_match.group(1), money_match.group(1)
        clean_money = money.replace(",", "").replace("，", "")
        for exist_f, exist_money in entity_money_map.get(hosp, []):
            if clean_money != exist_money.replace(",", "").replace("，", ""):
                conflicts.append({
                    "id": f"conflict_{get_finding_hash(exist_f)[:6]}_{get_finding_hash(f)[:6]}",
                    "type": "AMOUNT_MISMATCH",
                    "entity": hosp,
                    "description": f"针对【{hosp}】的涉案金额出现存在前后矛盾。请人工审核。",
                    "item_a": exist_f,
                    "item_b": f,
                })
        entity_money_map.setdefault(hosp, []).append((f, money))
    return conflicts


def _detect_conclusion_conflicts(valid_findings: List[str]) -> List[Dict[str, Any]]:
    conflicts: List[Dict[str, Any]] = []
    compliance_map: Dict[str, List[Tuple[str, str]]] = {}
    for f in valid_findings:
        hosp_match = re.search(r"([\u4e00-\u9fff]{2,10}(?:医院|门诊|诊所))", f)
        if not (hosp_match and hasattr(f, "lower")):
            continue
        t = f.lower()
        is_violating = any(x in t for x in ("存在违规", "构成违规", "涉嫌骗保", "确实存在", "违规嫌疑"))
        is_compliant = any(x in t for x in ("不构成违规", "不存在违规", "符合规范", "合规", "未发现违规"))
        if not (is_violating or is_compliant):
            continue
        hosp = hosp_match.group(1)
        status = "VIOLATION" if is_violating else "COMPLIANT"
        for exist_f, exist_status in compliance_map.get(hosp, []):
            if exist_status != status:
                conflicts.append({
                    "id": f"conflict_{get_finding_hash(exist_f)[:6]}_{get_finding_hash(f)[:6]}",
                    "type": "CONCLUSION_MISMATCH",
                    "entity": hosp,
                    "description": f"针对【{hosp}】的违规判定结论出现矛盾。请人工审核。",
                    "item_a": exist_f,
                    "item_b": f,
                })
        compliance_map.setdefault(hosp, []).append((f, status))
    return conflicts


def detect_conflicts(findings: List[str]) -> List[Dict[str, Any]]:
    """扫描 Findings，检测同一主体在金额或合规判定上的前后矛盾。"""
    valid_findings = [f.strip() for f in findings if len(f.strip()) > 5 and not is_discarded(f.strip())]
    return _detect_amount_conflicts(valid_findings) + _detect_conclusion_conflicts(valid_findings)

def get_filtered_findings(findings: List[str]) -> List[str]:
    """获取过滤掉已被用户废弃的 findings 后的一份列表"""
    return [f for f in findings if not is_discarded(f)]
