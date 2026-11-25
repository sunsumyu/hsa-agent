from __future__ import annotations
from typing import Any, Dict, List, Optional
from app.multi_agent.contracts import ExecutionTier, OrchestrationPlan, SubTaskSpec

_GRAPH_KEYWORDS = ("团伙", "欺诈环", "共用手机", "共享手机", "共用联系方式", "图谱", "窝案", "关联网络")
_SWEEP_KEYWORDS = ("全面体检", "综合飞检", "全面飞检", "全维度", "多维排查", "专项体检", "同时排查")
_REVIEW_KEYWORDS = ("临床合理性", "合规适应症", "剔除误报", "豁免", "抗辩", "临床指征")

_SWEEP_DIMENSIONS = [
    ("gender_drug", "性别用药互斥排查", "排查 fqz_fymx_test 中男性参保人开具妇科专属药品的记录笔数与金额", ("妇科", "性别")),
    ("male_iud", "宫内节育器恶性欺诈排查", "排查 fqz_fymx_test 中男性参保人使用宫内节育系统的记录笔数与金额", ("节育", "上环")),
    ("refund_reversal", "负数退费冲正核查", "核查 fqz_fymx_test 中明细金额小于 0 的退费冲正笔数与累计金额", ("退费", "冲正", "负数")),
    ("high_fee_outlier", "单笔大额离群核查", "筛查 fqz_fymx_test 中单笔费用 >= 1000 元的高额离群记录数与金额", ("大额", "离群", "1000")),
]


def _extract_sweep_subtasks(query: str) -> List[SubTaskSpec]:
    matched = [
        SubTaskSpec(subtask_id=sid, focus_title=title, query_instruction=inst)
        for sid, title, inst, kws in _SWEEP_DIMENSIONS
        if any(k in query for k in kws)
    ]
    if len(matched) >= 2:
        return matched
    return [
        SubTaskSpec(subtask_id=sid, focus_title=title, query_instruction=inst)
        for sid, title, inst, _ in _SWEEP_DIMENSIONS[:3]
    ]


def classify_execution_plan(
    query: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> OrchestrationPlan:
    """基于审计问题语义确定 L0 / L1 / L2 执行层级与专家编排契约。"""
    meta = metadata or {}
    q = (query or "").strip()
    if meta.get("synthesis_done") or meta.get("fast_route_id"):
        return OrchestrationPlan(tier=ExecutionTier.L0_FAST, reason="命中前置缓存或快路规则")

    has_graph = any(k in q for k in _GRAPH_KEYWORDS)
    has_sweep = any(k in q for k in _SWEEP_KEYWORDS)
    has_review = any(k in q for k in _REVIEW_KEYWORDS)

    if has_graph:
        subtasks = [SubTaskSpec(subtask_id="graph_ring_sql", focus_title="团伙侧载结算金额核算", query_instruction=q)]
        return OrchestrationPlan(
            tier=ExecutionTier.L2_MULTI_AGENT,
            requires_graph=True,
            requires_policy_review=True,
            subtasks=subtasks,
            reason="检测到跨库图谱团伙欺诈关联特征",
        )

    if has_sweep:
        return OrchestrationPlan(
            tier=ExecutionTier.L2_MULTI_AGENT,
            requires_graph=False,
            requires_policy_review=True,
            subtasks=_extract_sweep_subtasks(q),
            reason="检测到多维并发综合飞检任务",
        )

    if has_review:
        subtasks = [SubTaskSpec(subtask_id="primary_sql", focus_title="初筛疑点数据取证", query_instruction=q)]
        return OrchestrationPlan(
            tier=ExecutionTier.L2_MULTI_AGENT,
            requires_graph=False,
            requires_policy_review=True,
            subtasks=subtasks,
            reason="检测到临床合理性豁免与法规交叉复核需求",
        )

    return OrchestrationPlan(tier=ExecutionTier.L1_SOLO_SQL, reason="常规单域结构化审计查询")
