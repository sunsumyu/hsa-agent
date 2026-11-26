"""
[V4.9.6] MemPalace 证据实体抽取与图谱管理深模块 (EvidenceKnowledgeGraphManager)

将 Agent 推演产生的 Findings 文本列表，解析为知识图谱节点和连接边，
供前端 ECharts 图谱组件直接消费；同时支持多会话隔离、冲突检测聚合与平滑降级。
"""
from __future__ import annotations

import re
import hashlib
import threading
from collections import OrderedDict
from typing import List, Dict, Any, Optional
from loguru import logger

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
    r"([\u4e00-\u9fff]{2,12}(?:医院|诊所|卫生院|保健院|卫生室|门诊|医疗|中心))",
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


class EvidenceKnowledgeGraphManager:
    """
    [Matt Pocock Deep Module]
    医保证据知识图谱与线索管理器：
    1. 实体抽取与图谱生成（纯逻辑计算，支持正则与 spaCy 混合识别）；
    2. 多会话线程安全状态存储（LRU 隔离不同 session_id）；
    3. 冲突检测联动（统一向 conflict_detector 委托）；
    4. 兜底回退自愈（空实体占位、spaCy 缺失降级）。
    """

    def __init__(self, max_sessions: int = 500):
        self._nlp = None
        self._nlp_checked = False
        self._max_sessions = max_sessions
        self._session_findings: OrderedDict[str, List[str]] = OrderedDict()
        self._latest_session_id: str = ""
        self._lock = threading.Lock()

    def get_nlp(self):
        """惰性加载 spaCy 中文模型，加载失败时优雅降级并缓存状态"""
        if not self._nlp_checked:
            try:
                import spacy
                self._nlp = spacy.load("zh_core_web_sm")
                logger.info("✅ spaCy (zh_core_web_sm) 加载成功，开启混合实体识别模式。")
            except Exception:
                logger.warning("⚠️ spaCy 或 zh_core_web_sm 未就绪，系统降级为纯正则识别模式。")
                self._nlp = False
            self._nlp_checked = True
        return self._nlp

    @staticmethod
    def _stable_id(text: str, prefix: str) -> str:
        """用短哈希生成稳定的节点 ID，避免重复"""
        h = hashlib.md5(text.encode()).hexdigest()[:8]
        return f"{prefix}_{h}"

    @staticmethod
    def _extract_by_patterns(text: str, patterns: List[str]) -> List[str]:
        results = []
        for p in patterns:
            found = re.findall(p, text)
            for f in found:
                clean = f.strip().rstrip("，。；")
                if clean and len(clean) >= 2:
                    results.append(clean)
        return list(dict.fromkeys(results))  # unique-preserve-order

    def _extract_hospitals_and_patients(
        self, text: str, fid: str, add_node: Any, add_edge: Any
    ) -> List[str]:
        hospitals = self._extract_by_patterns(text, HOSPITAL_PATTERNS)
        nlp = self.get_nlp()
        if nlp:
            try:
                for ent in nlp(text).ents:
                    if ent.label_ in ("FAC", "ORG") and ent.text not in hospitals and len(ent.text) >= 4:
                        hospitals.append(ent.text)
                    elif ent.label_ == "PERSON":
                        masked = ent.text[0] + "**" if len(ent.text) > 1 else ent.text + "*"
                        pid = self._stable_id(ent.text, "P")
                        add_node(pid, masked, "patient", value=2.0)
                        add_edge(pid, fid, "关联")
            except Exception as e:
                logger.debug(f"[EvidenceGraph] spaCy NER 提取跳过: {e}")

        for hosp in hospitals:
            hid = self._stable_id(hosp, "H")
            add_node(hid, hosp, "hospital", value=3.0)
            add_edge(hid, fid, "涉及")
        for pat in self._extract_by_patterns(text, PATIENT_PATTERNS):
            pid = self._stable_id(pat, "P")
            add_node(pid, f"患者 {pat[:10]}", "patient", value=2.0)
            add_edge(pid, fid, "关联")
            for hosp in hospitals:
                add_edge(pid, self._stable_id(hosp, "H"), "就诊于")
        return hospitals

    def _extract_policies_amounts_records(
        self, text: str, idx: int, fid: str, hospitals: List[str], add_node: Any, add_edge: Any
    ) -> None:
        for pol in self._extract_by_patterns(text, POLICY_PATTERNS):
            pol_id = self._stable_id(pol, "PL")
            add_node(pol_id, pol[:20], "policy", value=2.5)
            add_edge(fid, pol_id, "违反")
        for amt_str in self._extract_by_patterns(text, AMOUNT_PATTERNS)[:2]:
            try:
                amt_val = float(re.sub(r"[，,]", "", amt_str))
                if amt_val < 0.01:
                    continue
                aid = self._stable_id(amt_str + str(idx), "A")
                add_node(aid, f"¥ {amt_val:,.0f}", "amount", value=max(1.5, amt_val / 10000))
                add_edge(fid, aid, "金额")
            except (ValueError, AttributeError) as exc:
                logger.debug(f"[EvidenceGraph] 金额解析跳过 ({amt_str!r}): {exc}")
        for rec in self._extract_by_patterns(text, RECORD_PATTERNS):
            rid = self._stable_id(rec, "R")
            add_node(rid, f"记录 {rec}", "record", value=1.5)
            add_edge(fid, rid, "依据")
            for hosp in hospitals:
                add_edge(rid, self._stable_id(hosp, "H"), "属于")

    def extract_graph(self, findings: List[str]) -> Dict[str, Any]:
        """核心方法：将 Findings 文本列表转换为 ECharts graph 数据。"""
        try:
            from app.skills.security.conflict_detector import get_filtered_findings
            findings = get_filtered_findings(findings)
        except ImportError as exc:
            logger.debug(f"[EvidenceGraph] conflict_detector filter skipped: {exc}")

        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, str]] = []
        finding_ids: List[str] = []

        def add_node(node_id: str, name: str, category: str, value: float = 1.0, tooltip: str = "") -> str:
            if node_id not in nodes:
                nodes[node_id] = {
                    "id": node_id,
                    "name": name[:24],
                    "category": CAT_INDEX.get(category, 5),
                    "value": value,
                    "symbolSize": max(20, min(60, value * 2)),
                    "tooltip": tooltip or name,
                }
            return node_id

        def add_edge(src: str, dst: str, label: str) -> None:
            edges.append({"source": src, "target": dst, "label": label})

        for idx, finding in enumerate(findings):
            if not finding or len(finding.strip()) < 5:
                continue
            text = finding.strip()
            fid = self._stable_id(text, "F")
            add_node(fid, f"发现 #{idx+1}", "finding", value=1.0, tooltip=text[:120])
            finding_ids.append(fid)
            hospitals = self._extract_hospitals_and_patients(text, fid, add_node, add_edge)
            self._extract_policies_amounts_records(text, idx, fid, hospitals, add_node, add_edge)

        if len(nodes) <= len(finding_ids) and finding_ids:
            add_node("CENTER", "稽核中心", "policy", value=5.0)
            for fid in finding_ids:
                add_edge("CENTER", fid, "包含")

        return {"nodes": list(nodes.values()), "edges": edges, "categories": CATEGORIES, "total": len(nodes)}

    def record_session_findings(self, session_id: str, findings: List[str]) -> None:
        """记录会话线索（线程安全，支持容量淘汰）"""
        with self._lock:
            sid = session_id or "default_session"
            if sid in self._session_findings:
                self._session_findings.move_to_end(sid)
            self._session_findings[sid] = list(findings or [])
            self._latest_session_id = sid

            while len(self._session_findings) > self._max_sessions:
                self._session_findings.popitem(last=False)

            global _latest_findings, _latest_session_id
            _latest_findings = self._session_findings[sid]
            _latest_session_id = sid

    def get_session_findings(self, session_id: Optional[str] = None) -> List[str]:
        """获取指定会话（或最新会话）的 findings 列表"""
        with self._lock:
            if session_id:
                return list(self._session_findings.get(session_id, []))
            if self._latest_session_id and self._latest_session_id in self._session_findings:
                return list(self._session_findings[self._latest_session_id])
            return list(_latest_findings)

    def get_session_graph(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """获取指定会话（或最新会话）的可视化图谱"""
        target_session = session_id
        with self._lock:
            if not target_session:
                target_session = self._latest_session_id
            if target_session and target_session not in self._session_findings:
                return {
                    "nodes": [],
                    "edges": [],
                    "categories": CATEGORIES,
                    "total": 0,
                    "message": f"会话 {target_session} 的图谱尚未生成，请先发起稽核推演",
                }
            findings = self._session_findings.get(target_session, _latest_findings)

        return self.extract_graph(findings)

    def detect_session_conflicts(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """检测指定会话（或最新会话）中的逻辑冲突"""
        findings = self.get_session_findings(session_id)
        from app.skills.security.conflict_detector import detect_conflicts
        return detect_conflicts(findings)

    def clear(self) -> None:
        """清空所有会话缓存（单元测试重置）"""
        with self._lock:
            self._session_findings.clear()
            self._latest_session_id = ""
            global _latest_findings, _latest_session_id
            _latest_findings = []
            _latest_session_id = ""


# ── 全局单例与向后兼容接口 ────────────────────────────────────────────────────────
evidence_graph_manager = EvidenceKnowledgeGraphManager()

_NLP = None
def get_nlp():
    return evidence_graph_manager.get_nlp()

_latest_findings: List[str] = []
_latest_session_id: str = ""

def extract_graph(findings: List[str]) -> Dict[str, Any]:
    return evidence_graph_manager.extract_graph(findings)

def update_latest_findings(session_id: str, findings: List[str]):
    evidence_graph_manager.record_session_findings(session_id, findings)

def get_latest_graph(session_id: str = None) -> Dict[str, Any]:
    return evidence_graph_manager.get_session_graph(session_id)
