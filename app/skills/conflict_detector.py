"""
[V4.9.6] MemPalace 记忆冲突检测器 (Conflict Detector)

分析 Agent 的发现线索 (Findings) 中是否存在事实冲突或前后矛盾。
"""
import re
import hashlib
from typing import List, Dict, Any, Tuple

# 记录被用户解决并固化的冲突决策
# 结构: { finding_hash: boolean }  (True代表采纳，False代表废弃)
_resolved_findings = {}

def get_finding_hash(finding: str) -> str:
    return hashlib.md5(finding.strip().encode()).hexdigest()

def mark_resolved(finding: str, accepted: bool):
    """记录人类审计员关于某项证据是否保留的决策"""
    _resolved_findings[get_finding_hash(finding)] = accepted

def is_discarded(finding: str) -> bool:
    """该条目是否被标记为废弃"""
    return _resolved_findings.get(get_finding_hash(finding)) is False

def detect_conflicts(findings: List[str]) -> List[Dict[str, Any]]:
    """
    扫描 Findings，检测可能存在的矛盾。
    简单的规则引擎：
    1. 查找包含同一家医院/同一个患者，但得出的涉案金额或违规类型完全不同。
    2. 或前后推翻的结论（如“不构成违规” vs “存在违规”）。
    3. 已被判定废弃的 findings 将直接被跳过，不再参与冲突计算。
    """
    conflicts = []
    
    # 提取有效 findings
    valid_findings = []
    for f in findings:
        clean = f.strip()
        if len(clean) > 5 and not is_discarded(clean):
            valid_findings.append(clean)
            
    # 规则 1：金额矛盾。同一个主体的涉案金额出现了分歧
    # 此处为演示级别的实体提取，对同一行内的医院和金额做绑定
    entity_money_map: Dict[str, List[str]] = {}
    
    for idx, f in enumerate(valid_findings):
        # 寻找机构名称
        hosp_match = re.search(r"([\u4e00-\u9fff]{2,10}(?:医院|门诊|诊所))", f)
        # 寻找涉案或违规金额
        money_match = re.search(r"(?:金额|违规金额|涉案金额|涉及.*?金额).*?([\d,，\.]+)\s*(?:元|万元)", f)
        
        if hosp_match and money_match:
            hosp = hosp_match.group(1)
            money = money_match.group(1)
            
            if hosp not in entity_money_map:
                entity_money_map[hosp] = [(f, money)]
            else:
                # 检查金额是否不同
                existing = entity_money_map[hosp]
                # 简单清洗并比对
                clean_money = money.replace(",", "").replace("，", "")
                for exist_f, exist_money in existing:
                    clean_exist = exist_money.replace(",", "").replace("，", "")
                    if clean_money != clean_exist:
                        # 发现冲突！
                        conflict_id = f"conflict_{get_finding_hash(exist_f)[:6]}_{get_finding_hash(f)[:6]}"
                        conflicts.append({
                            "id": conflict_id,
                            "type": "AMOUNT_MISMATCH",
                            "entity": hosp,
                            "description": f"针对【{hosp}】的涉案金额出现存在前后矛盾。请人工审核。",
                            "item_a": exist_f,
                            "item_b": f
                        })
                entity_money_map[hosp].append((f, money))
                
    # 规则 2：结论矛盾（判定违规 vs 判定合规）
    compliance_map = {}
    for idx, f in enumerate(valid_findings):
        hosp_match = re.search(r"([\u4e00-\u9fff]{2,10}(?:医院|门诊|诊所))", f)
        if hasattr(f, 'lower'):
            t = f.lower()
            is_violating = any(x in t for x in ["存在违规", "构成违规", "涉嫌骗保", "确实存在", "违规嫌疑"])
            is_compliant = any(x in t for x in ["不构成违规", "不存在违规", "符合规范", "合规", "未发现违规"])
            
            if hosp_match and (is_violating or is_compliant):
                hosp = hosp_match.group(1)
                status = "VIOLATION" if is_violating else "COMPLIANT"
                
                if hosp not in compliance_map:
                    compliance_map[hosp] = [(f, status)]
                else:
                    for exist_f, exist_status in compliance_map[hosp]:
                        if exist_status != status:
                            conflict_id = f"conflict_{get_finding_hash(exist_f)[:6]}_{get_finding_hash(f)[:6]}"
                            conflicts.append({
                                "id": conflict_id,
                                "type": "CONCLUSION_MISMATCH",
                                "entity": hosp,
                                "description": f"针对【{hosp}】的违规判定结论出现矛盾。请人工审核。",
                                "item_a": exist_f,
                                "item_b": f
                            })
                    compliance_map[hosp].append((f, status))

    return conflicts

def get_filtered_findings(findings: List[str]) -> List[str]:
    """获取过滤掉已被用户废弃的 findings 后的一份列表"""
    return [f for f in findings if not is_discarded(f)]
