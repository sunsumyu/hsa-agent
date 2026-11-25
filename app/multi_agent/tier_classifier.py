from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.registry.archetype_registry import ArchetypeCategory, archetype_registry
from app.multi_agent.contracts import ExecutionTier, OrchestrationPlan, SubTaskSpec

_GRAPH_KEYWORDS = ("团伙", "欺诈环", "共用手机", "共享手机", "共用联系方式", "图谱", "窝案", "关联网络")
_SWEEP_KEYWORDS = ("全面体检", "综合飞检", "全面飞检", "全维度", "多维排查", "专项体检", "同时排查")
_REVIEW_KEYWORDS = ("临床合理性", "合规适应症", "剔除误报", "豁免", "抗辩", "临床指征")

_SWEEP_SPECS = (
    ("gender_drug", "性别用药互斥排查", ArchetypeCategory.GENDER_CONFLICT, "排查男性参保人开具妇科专属药品的记录笔数与金额", ("妇科", "性别")),
    ("male_iud", "宫内节育器恶性欺诈排查", ArchetypeCategory.GENDER_CONFLICT, "排查男性参保人使用宫内节育系统的记录笔数与金额", ("节育", "上环")),
    ("refund_reversal", "负数退费冲正核查", ArchetypeCategory.REVERSAL_REFUND, "核查明细金额小于 0 的退费冲正笔数与累计金额", ("退费", "冲正", "负数")),
    ("high_fee_outlier", "单笔大额离群核查", ArchetypeCategory.RANKING, "筛查单笔费用 >= 1000 元的高额离群记录数与金额", ("大额", "离群", "1000")),
)


def _resolve_target_table(category: ArchetypeCategory) -> Optional[str]:
    for arch in archetype_registry._archetypes:
        if arch.category == category and arch.target_tables:
            return arch.target_tables[0]
    return None


def _build_subtask(sid: str, title: str, category: ArchetypeCategory, action: str) -> SubTaskSpec:
    table = _resolve_target_table(category)
    instruction = f"针对目标表 `{table}` {action}" if table else action
    return SubTaskSpec(subtask_id=sid, focus_title=title, query_instruction=instruction)


def _extract_sweep_subtasks(query: str) -> List[SubTaskSpec]:
    matched = [
        _build_subtask(sid, title, cat, action)
        for sid, title, cat, action, kws in _SWEEP_SPECS
        if any(k in query for k in kws)
    ]
    if len(matched) >= 2:
        return matched
    return [_build_subtask(sid, title, cat, action) for sid, title, cat, action, _ in _SWEEP_SPECS[:3]]


def _make_l2_plan(reason: str, subtasks: List[SubTaskSpec], requires_graph: bool = False) -> OrchestrationPlan:
    return OrchestrationPlan(
        tier=ExecutionTier.L2_MULTI_AGENT,
        requires_graph=requires_graph,
        requires_policy_review=True,
        subtasks=subtasks,
        reason=reason,
    )


def classify_execution_plan(
    query: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> OrchestrationPlan:
    """基于审计问题语义确定 L0 / L1 / L2 执行层级与专家编排契约。"""
    meta = metadata or {}
    q = (query or "").strip()
    if meta.get("synthesis_done") or meta.get("fast_route_id"):
        return OrchestrationPlan(tier=ExecutionTier.L0_FAST, reason="命中前置缓存或快路规则")

    if any(k in q for k in _GRAPH_KEYWORDS):
        subtask = SubTaskSpec(subtask_id="graph_ring_sql", focus_title="团伙侧载结算金额核算", query_instruction=q)
        return _make_l2_plan("检测到跨库图谱团伙欺诈关联特征", [subtask], requires_graph=True)

    if any(k in q for k in _SWEEP_KEYWORDS):
        return _make_l2_plan("检测到多维并发综合飞检任务", _extract_sweep_subtasks(q))

    if any(k in q for k in _REVIEW_KEYWORDS):
        subtask = SubTaskSpec(subtask_id="primary_sql", focus_title="初筛疑点数据取证", query_instruction=q)
        return _make_l2_plan("检测到临床合理性豁免与法规交叉复核需求", [subtask])

    return OrchestrationPlan(tier=ExecutionTier.L1_SOLO_SQL, reason="常规单域结构化审计查询")
