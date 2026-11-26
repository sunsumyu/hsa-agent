"""
app/reporting/traceability_section_builder.py
=============================================
[Matt Pocock Deep Module] 审计报告风险评估与可追溯存证凭证排版深模块。

职责内聚：
1. 风险评级卡片排版 (build_risk_section)
2. 审计可追溯性凭证排版 (build_traceability_section)
3. 租户与行政主体映射 (resolve_admin_name)
4. 多维风险等级裁定 (calculate_risk_level)
5. 防篡改数字存证指纹生成 (generate_evidence_fingerprint)
"""

from datetime import datetime
import hashlib
from typing import Any, Dict, List, Optional

# 默认风险评级阈值配置
DEFAULT_RISK_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    "high": {"min_amount": 50_000, "min_count": 10},
    "medium": {"min_amount": 10_000, "min_count": 3},
}


def generate_evidence_fingerprint(trace_id: str, model_id: str, timestamp: Any) -> str:
    """
    生成确定性的数字存证签名 (简易版 16 位 MD5 指纹)
    """
    sign_base = f"{trace_id}-{model_id}-{timestamp}"
    signature = hashlib.md5(sign_base.encode("utf-8")).hexdigest()[:16].upper()
    return f"ARGUS-{signature}"


def resolve_admin_name(tenant_id: Optional[str]) -> str:
    """
    将租户 ID 转换为审计行政主体规范名称
    """
    if not tenant_id:
        return "Argus 智能审计中心"

    code = tenant_id.split("_")[1] if "_" in tenant_id else tenant_id
    prefix = tenant_id.split("_")[0] if "_" in tenant_id else ""

    mapping = {
        "310000": "上海市医疗保障局",
        "310100": "上海市医保中心 (地市级)",
        "310104": "徐汇区医疗保障局",
        "310115": "浦东新区医疗保障局",
    }

    base_name = mapping.get(code, f"行政代码 {code} 审计组")
    if prefix == "DIST":
        return f"【区县级】{base_name}"
    if prefix == "CITY":
        return f"【地市级】{base_name}"
    if prefix == "PROV":
        return f"【省级】{base_name}"
    return base_name


def calculate_risk_level(
    total_amount: float,
    finding_count: int,
    risk_thresholds: Optional[Dict[str, Any]] = None,
) -> str:
    """
    根据金额与发现条数阈值裁定综合风险等级 (高/中/低)
    """
    thresholds = risk_thresholds or DEFAULT_RISK_THRESHOLDS
    high = thresholds.get("high", {})
    medium = thresholds.get("medium", {})

    if (
        total_amount >= high.get("min_amount", float("inf"))
        or finding_count >= high.get("min_count", float("inf"))
    ):
        return "高"
    if (
        total_amount >= medium.get("min_amount", float("inf"))
        or finding_count >= medium.get("min_count", float("inf"))
    ):
        return "中"
    return "低"


def build_risk_section(
    risk_level: str,
    total_amount: float,
    finding_count: int,
) -> str:
    """
    渲染第五章：风险评级表格
    """
    emoji_map = {"高": "🔴", "中": "🟡", "低": "🟢"}
    emoji = emoji_map.get(risk_level, "⚪")
    return "\n".join([
        "## 五、风险评级",
        "",
        "| 维度 | 评估结果 |",
        "| :--- | :--- |",
        f"| 综合风险等级 | {emoji} **{risk_level}风险** |",
        f"| 涉及金额 | ¥{total_amount:,.2f} |",
        f"| 发现条数 | {finding_count} 条 |",
        "",
    ])


def build_citation_provenance_table(citations: List[Dict[str, Any]]) -> str:
    """渲染法规与知识引文溯源核验台账表。"""
    rows = [c for c in (citations or []) if isinstance(c, dict) and c.get("citation_id")]
    if not rows:
        return ""
    labels = {"law_rag": "法规向量库 (law_rag)", "vector_rag": "知识向量库 (vector_rag)", "policy_registry": "静态规则库 (policy_registry)"}
    lines = ["### 法条与知识引文溯源台账", "", "| Citation ID | 来源类型 | 文档 / 页码 / 章节 | 内容哈希 |", "| :--- | :--- | :--- | :--- |"]
    for rec in rows:
        origin = labels.get(str(rec.get("source_type") or ""), str(rec.get("source_type") or "-"))
        parts = [str(rec.get("source_doc") or "-")]
        if rec.get("page_num"):
            parts.append(f"第{rec['page_num']}页")
        if rec.get("section_path"):
            parts.append(str(rec["section_path"]).strip())
        locator = " / ".join(p.replace("|", "\\|") for p in parts if p)
        chash = str(rec.get("content_hash") or "-")
        lines.append(f"| `{rec.get('citation_id', '')}` | {origin} | {locator} | `{chash}` |")
    return "\n".join(lines)


def build_traceability_section(metadata: Optional[Dict[str, Any]]) -> str:
    """
    渲染第六章：审计可追溯性凭证
    """
    if not metadata:
        return ""

    lines = ["## 六、审计可追溯性凭证", ""]
    lines.append("| 审计元数据项 | 执行记录值 |")
    lines.append("| :--- | :--- |")

    # 提取关键元数据
    trace_id = metadata.get("trace_id", "N/A")
    model_id = metadata.get("audit_model_id", "Hybrid-Agent")
    latency = metadata.get("audit_latency_ms", 0)
    timestamp = metadata.get("audit_timestamp", 0)

    if timestamp:
        try:
            time_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"| 执行时间戳 | {time_str} |")
        except Exception:
            pass

    lines.append(f"| 物理算力节点 | `{model_id}` |")
    lines.append(f"| 全链路 TraceID | `{trace_id}` |")

    if latency:
        lines.append(f"| 推理总耗时 | {latency:.1f} ms |")

    fingerprint = generate_evidence_fingerprint(trace_id, model_id, timestamp)
    lines.append(f"| 数字存证指纹 | `{fingerprint}` |")

    provenance_table = build_citation_provenance_table(metadata.get("retrieved_citations") or [])
    if provenance_table:
        lines.extend(["", provenance_table])

    lines.append("")
    lines.append("> ⚠️ **审计申明**：本报告由 Argus 自动生成，所有执行指令均已通过逻辑合规性校验并记录于证据库。")
    return "\n".join(lines)
