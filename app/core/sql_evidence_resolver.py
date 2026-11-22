"""
app/core/sql_evidence_resolver.py
=================================
[Deep Module] 审计核心 SQL 推断与用户命题解析深模块。

设计哲学 (Matt Pocock Deep Module Principles):
    - 窄接口 (Narrow Interface):
      仅公开 `resolve_core_audit_sql` 与 `resolve_user_query` 两个纯函数。
    - 消除重复与收缩范围:
      彻底根除 CoderAgent、PlannerAgent 等节点在状态回退与保全时重复编写的 10 行指标加权与逆向扫描逻辑。
    - 无副作用与独立测试:
      不依赖具体的 Agent 图或网络环境，确保 100% 可推导性。
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Sequence, Callable
from langchain_core.messages import HumanMessage, BaseMessage


# 医保核心聚合与结算指标关键字特征集
_CORE_METRIC_KEYWORDS = frozenset([
    "SUM(", "AVG(", "MEDFEE", "TOTAL", "AMT", "FEE", "ROUND(SUM", "COUNT(DISTINCT"
])


def resolve_core_audit_sql(
    history_sql: Sequence[str],
    is_probe_fn: Optional[Callable[[str], bool]] = None
) -> str:
    """
    从历史执行 SQL 列表中精确推断最具代表性的物理业务/对碰 SQL。
    
    推断优先级：
    1. 排除探针查询 (Probe Queries) 后的最后一条核心指标聚合 SQL (含 SUM/AVG/MEDFEE/AMT 等)；
    2. 若无指标聚合，回退到最后一条普通非探针业务查询；
    3. 若全为探针查询，安全保底返回最后一条历史 SQL；
    4. 列表为空返回空字符串。
    """
    if not history_sql:
        return ""

    # 1. 过滤探针探路 SQL
    if is_probe_fn:
        audit_queries = [s for s in history_sql if s and not is_probe_fn(s)]
    else:
        audit_queries = [s for s in history_sql if s]

    # 2. 识别含有核心金额、费用或聚合指标的 SQL
    metric_queries = [
        s for s in audit_queries
        if any(kw in s.upper() for kw in _CORE_METRIC_KEYWORDS)
    ]

    if metric_queries:
        return metric_queries[-1]
    elif audit_queries:
        return audit_queries[-1]
    else:
        return history_sql[-1]


def resolve_user_query(
    state: Optional[Dict[str, Any]] = None,
    messages: Optional[Sequence[Any]] = None,
    max_chars: int = 300,
    fallback_keys: Optional[Sequence[str]] = None
) -> str:
    """
    单一事实源 (SSOT) 解析当前轮次确定的用户提问或命题。
    
    解析优先级：
    1. `state["current_turn_query"]` (当前轮消解后的自包含独立命题)
    2. `state["metadata"]["user_question"]`
    3. `messages` 或 `state["messages"]` 倒序扫描出的第一条用户消息 (支持 HumanMessage, tuple, dict)
    4. `state` 中 fallback_keys 指定的降级字段 (如 human_input, question, user_query)
    """
    user_q = ""
    st = state or {}

    # 优先级 1: 消解后的当前轮自包含命题
    if st.get("current_turn_query"):
        user_q = str(st["current_turn_query"])

    # 优先级 2: 元数据初始提问
    if not user_q and (st.get("metadata") or {}).get("user_question"):
        user_q = str(st["metadata"]["user_question"])

    # 优先级 3: 逆向扫描消息列表
    if not user_q:
        candidate_msgs = messages if messages is not None else st.get("messages", [])
        for m in reversed(candidate_msgs):
            if isinstance(m, tuple) and len(m) >= 2 and str(m[0]).lower() in ("user", "human"):
                user_q = str(m[1])
                break
            elif isinstance(m, dict):
                role = str(m.get("role") or m.get("type") or "").lower()
                if role in ("user", "human"):
                    user_q = str(m.get("content") or m.get("text") or "")
                    break
            elif isinstance(m, HumanMessage) or (hasattr(m, "type") and getattr(m, "type", "").lower() in ("human", "user")):
                user_q = str(getattr(m, "content", ""))
                break

    # 优先级 4: 宽容性备选键降级
    if not user_q and fallback_keys:
        for k in fallback_keys:
            if st.get(k):
                user_q = str(st[k])
                break

    return (user_q or "").strip()[:max_chars]

