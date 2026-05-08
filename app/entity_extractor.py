"""
[V4.9.6] MemPalace 证据实体抽取器 (Entity Extractor)

将 Agent 推演产生的 Findings 文本列表，解析为图谱节点和连接边，
供前端 ECharts 图谱组件直接消费。
"""
import re
import hashlib
import logging
from typing import List, Dict, Any, Tuple
from loguru import logger

# [V47.6] 引入 spaCy 混合识别：参考 hello-agents 的小模型方案
_NLP = None
def get_nlp():
    global _NLP
    if _NLP is None:
        try:
            import spacy
            # 优先加载中文小模型，用于发现正则无法覆盖的机构和人名
            _NLP = spacy.load("zh_core_web_sm")
            logger.info("✅ spaCy (zh_core_web_sm) 加载成功，开启混合实体识别模式。")
        except Exception:
            logger.warning("⚠️ spaCy 或 zh_core_web_sm 未就绪，系统降级为纯正则识别模式。")
            _NLP = False
    return _NLP

# ── 类别定义 ───────────────────────────────────────────────────────────────────
CATEGORIES = [
    {"name": "hospital",  "itemStyle": {"color": "#ef4444"}},  # 医疗机构 - 红
    {"name": "patient",   "itemStyle": {"color": "#f59e0b"}},  # 患者 - 橙
    {"name": "policy",    "itemStyle": {"color": "#3b82f6"}},  # 政策规则 - 蓝
    {"name": "record",    "itemStyle": {"color": "#8b5cf6"}},  # 结算记录 - 紫
    {"name": "amount",    "itemStyle": {"color": "#22c55e"}},  # 涉案金额 - 绿
    {"name": "finding",   "itemStyle": {"color": "#64748b"}},  # 通用发现 - 灰
]
CAT_INDEX = {c["name"]: i for i, c in enumerate(CATEGORIES)}

# ── 正则模式 ───────────────────────────────────────────────────────────────────
HOSPITAL_PATTERNS = [
    r"([\u4e00-\u9fff]{2,12}(?:医院|诊所|卫生院|卫生室|门诊|医疗|中心))",
]
PATIENT_PATTERNS = [
    r"(?:患者|社保号|psn_no)[：:]\s*([A-Z0-9_\-]{4,20})",
    r"\b(P_[A-Z0-9_]+)\b",
    r"(?:社保卡号|参保人)[：:]?\s*([0-9]{8,18})",
]
POLICY_PATTERNS = [
    r"((?:超量开药|分解住院|重复收费|挂床住院|虚记药品|过度检查|串换|倒药|套保)[^，。；\n]{0,20})",
    r"((?:医保政策|报销规则|资质限制)[^，。；\n]{0,30})",
    r"违反[了]?\s*[《「]?([^》」，。；\n]{4,30})[》」]?",
]
AMOUNT_PATTERNS = [
    r"(?:涉案金额|违规金额|报销金额|申报金额)[：:为]?\s*([\d,，\.]+)\s*(?:元|万元)?",
    r"([\d,，\.]+)\s*元",
]
RECORD_PATTERNS = [
    r"(?:结算记录|住院记录|门诊记录|就诊记录)[#＃]?\s*([A-Z0-9\-]{4,20})",
    r"(?:单据|凭证|处方)[号]?[：:]?\s*([A-Z0-9\-]{4,20})",
]


def _stable_id(text: str, prefix: str) -> str:
    """用短哈希生成稳定的节点 ID，避免重复"""
    h = hashlib.md5(text.encode()).hexdigest()[:8]
    return f"{prefix}_{h}"


def _extract_by_patterns(text: str, patterns: List[str]) -> List[str]:
    results = []
    for p in patterns:
        found = re.findall(p, text)
        for f in found:
            clean = f.strip().rstrip("，。；")
            if clean and len(clean) >= 2:
                results.append(clean)
    return list(dict.fromkeys(results))  # unique-preserve-order


def extract_graph(findings: List[str]) -> Dict[str, Any]:
    """
    核心函数：将 Findings 文本列表转换为 ECharts graph 数据。

    Returns:
        {"nodes": [...], "edges": [...], "categories": [...]}
    """
    try:
        from app.conflict_detector import get_filtered_findings
        findings = get_filtered_findings(findings)
    except ImportError:
        pass

    nodes: Dict[str, Dict] = {}
    edges: List[Dict]      = []
    finding_ids: List[str] = []

    def add_node(node_id: str, name: str, category: str, value: float = 1.0,
                 tooltip: str = "") -> str:
        if node_id not in nodes:
            nodes[node_id] = {
                "id":       node_id,
                "name":     name[:24],  # 限制显示长度
                "category": CAT_INDEX.get(category, 5),
                "value":    value,
                "symbolSize": max(20, min(60, value * 2)),
                "tooltip":  tooltip or name,
            }
        return node_id

    def add_edge(src: str, dst: str, label: str):
        edges.append({"source": src, "target": dst, "label": label})

    # ── 处理每条 Finding ──────────────────────────────────────────────────────
    for idx, finding in enumerate(findings):
        if not finding or len(finding.strip()) < 5:
            continue

        text = finding.strip()
        fid  = _stable_id(text, "F")
        add_node(fid, f"发现 #{idx+1}", "finding", value=1.0, tooltip=text[:120])
        finding_ids.append(fid)

        # -- 提取医疗机构 --
        hospitals = _extract_by_patterns(text, HOSPITAL_PATTERNS)
        
        # [V47.6] spaCy 语义补充：识别非标准结尾的机构名
        nlp = get_nlp()
        if nlp:
            doc = nlp(text)
            for ent in doc.ents:
                if ent.label_ == "FAC" or ent.label_ == "ORG":
                    if ent.text not in hospitals and len(ent.text) >= 4:
                        hospitals.append(ent.text)
        
        for hosp in hospitals:
            hid = _stable_id(hosp, "H")
            add_node(hid, hosp, "hospital", value=3.0)
            add_edge(hid, fid, "涉及")

        # -- 提取患者 ID --
        patients = _extract_by_patterns(text, PATIENT_PATTERNS)
        
        # [V47.6] spaCy 脱敏补充：识别报告中的真实人名并强制脱敏
        if nlp:
            doc = nlp(text)
            for ent in doc.ents:
                if ent.label_ == "PERSON":
                    p_name = ent.text
                    # 只有当正则没抓到 ID 时，才用 spaCy 抓到的人名，且强制脱敏
                    masked_name = p_name[0] + "**" if len(p_name) > 1 else p_name + "*"
                    pid = _stable_id(p_name, "P")
                    add_node(pid, masked_name, "patient", value=2.0)
                    add_edge(pid, fid, "关联")
        for pat in patients:
            pid = _stable_id(pat, "P")
            add_node(pid, f"患者 {pat[:10]}", "patient", value=2.0)
            add_edge(pid, fid, "关联")
            # 患者与机构连接
            for hosp in hospitals:
                hid = _stable_id(hosp, "H")
                add_edge(pid, hid, "就诊于")

        # -- 提取政策/违规类型 --
        policies = _extract_by_patterns(text, POLICY_PATTERNS)
        for pol in policies:
            pol_id = _stable_id(pol, "PL")
            add_node(pol_id, pol[:20], "policy", value=2.5)
            add_edge(fid, pol_id, "违反")

        # -- 提取金额 --
        amounts = _extract_by_patterns(text, AMOUNT_PATTERNS)
        for amt_str in amounts[:2]:  # 最多取2个金额，避免噪音
            try:
                clean_amt = re.sub(r"[，,]", "", amt_str)
                amt_val = float(clean_amt)
                if amt_val < 0.01: continue
                aid = _stable_id(amt_str + str(idx), "A")
                add_node(aid, f"¥ {amt_val:,.0f}", "amount", value=max(1.5, amt_val / 10000))
                add_edge(fid, aid, "金额")
            except (ValueError, AttributeError):
                pass

        # -- 提取结算记录编号 --
        records = _extract_by_patterns(text, RECORD_PATTERNS)
        for rec in records:
            rid = _stable_id(rec, "R")
            add_node(rid, f"记录 {rec}", "record", value=1.5)
            add_edge(fid, rid, "依据")
            for hosp in hospitals:
                hid = _stable_id(hosp, "H")
                add_edge(rid, hid, "属于")

    # ── 如无任何实体，生成摘要占位节点 ───────────────────────────────────────
    if len(nodes) <= len(finding_ids) and finding_ids:
        summary_id = "CENTER"
        add_node(summary_id, "稽核中心", "policy", value=5.0)
        for fid in finding_ids:
            add_edge(summary_id, fid, "包含")

    return {
        "nodes":      list(nodes.values()),
        "edges":      edges,
        "categories": CATEGORIES,
        "total":      len(nodes),
    }


# ── 全局缓存：存储最新推演的 findings（由 agent_graph 写入）────────────────────
_latest_findings: List[str] = []
_latest_session_id: str     = ""

def update_latest_findings(session_id: str, findings: List[str]):
    """由 agent_graph 在每次推演完成后调用，更新证据缓存"""
    global _latest_findings, _latest_session_id
    _latest_findings   = findings
    _latest_session_id = session_id

def get_latest_graph(session_id: str = None) -> Dict[str, Any]:
    """获取最新推演图谱（或指定会话的图谱）"""
    if session_id and session_id != _latest_session_id:
        return {"nodes": [], "edges": [], "categories": CATEGORIES, "total": 0,
                "message": f"会话 {session_id} 的图谱尚未生成，请先发起稽核推演"}
    return extract_graph(_latest_findings)
