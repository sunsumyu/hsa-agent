"""
app/core/context/coreference_rules.py
=====================================
Coreference rewrite rules pipeline, shared dataclasses, and pipeline signal constants.
Extracted from coreference_rewriter.py to keep both modules concise and maintainable.
"""

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple
from loguru import logger


SIGNAL_ANAPHORA_EXPANDED = "anaphora_expanded"
SIGNAL_SUSPECT_BOUND = "suspect_entity_bound"
SIGNAL_SCENE_SWITCH = "scene_switch"
SIGNAL_CORRECTION = "correction"


@dataclass(frozen=True)
class TurnAnalysis:
    """
    单轮对话的确定性分析结果（意图分类 + 命题消解 + 实体绑定 + 管道信号）。
    保持旧三元组解包兼容：`query, turn_type, entities = resolve_coreference(...)`。
    """
    query: str
    turn_type: str
    entities: Tuple[str, ...] = ()
    signals: FrozenSet[str] = frozenset()
    matched_rules: Tuple[str, ...] = ()

    def __iter__(self):
        """向后兼容旧三元组解包协议 (query, turn_type, entities)"""
        return iter((self.query, self.turn_type, self.entities))


@dataclass(frozen=True)
class RewriteContext:
    """改写管道共享上下文（state 派生量预提取一次，规则间不重复读取）"""
    original_query: str
    state: Dict[str, Any]
    last_finding: Dict[str, Any]
    prev_resolved: str
    prefix_builder: Optional[Callable[[str], str]] = None
    entity_extractor: Optional[Callable[[Dict[str, Any]], Optional[str]]] = None


@dataclass(frozen=True)
class RuleOutcome:
    """单条规则产出：改写后的命题 + 是否生效 + 信号/实体增量"""
    query: str
    matched: bool
    signal: Optional[str] = None
    entities: Tuple[str, ...] = ()


class _RewriteRule:
    """命题改写规则基类：子类实现 apply，保证「触发->剥除->改写」原子耦合"""
    name: str = "base"

    def apply(self, query: str, ctx: RewriteContext) -> RuleOutcome:
        raise NotImplementedError


class _AnaphoraExpansionRule(_RewriteRule):
    """
    D1: 句首代词『上述/其中』展开为上一轮命题的限定从句。
    触发与剥除同源对齐（模式最长优先）：仅当句首代词被真实剥除后才前置上下文。
    """
    name = "anaphora_expansion"

    _STRIP_PATTERNS: Tuple[str, ...] = (
        r"^在上述违规记录中[，,]?",
        r"^上述违规记录中[，,]?",
        r"^上述违规记录[，,]?",
        r"^在上述记录中[，,]?",
        r"^上述记录中[，,]?",
        r"^上述记录[，,]?",
        r"^上述违规[，,]?",
        r"^其中[，,]?",
    )

    def apply(self, query: str, ctx: RewriteContext) -> RuleOutcome:
        builder = ctx.prefix_builder
        if builder is None:
            from app.core.context.coreference_rewriter import ContextualQueryRewriter
            builder = ContextualQueryRewriter._build_context_prefix

        for pattern in self._STRIP_PATTERNS:
            stripped = re.sub(pattern, "", query, count=1)
            if stripped == query:
                continue
            context_prefix = builder(ctx.prev_resolved)
            if not context_prefix:
                return RuleOutcome(query=query, matched=False)
            resolved = f"{context_prefix}{stripped.strip()}"
            logger.info(f"🔗 [CoreferenceRewriter] 展开代词『上述/其中』-> 「{resolved[:60]}...」")
            return RuleOutcome(query=resolved, matched=True, signal=SIGNAL_ANAPHORA_EXPANDED)
        return RuleOutcome(query=query, matched=False)


class _SuspectEntityRule(_RewriteRule):
    """D2: 嫌疑机构指代词（该医院/排名第一等）绑定到便签或最近发现中的具体实体。"""
    name = "suspect_entity_binding"

    _SUSPECT_KEYWORDS: Tuple[str, ...] = (
        "刚刚记入便签的重点嫌疑医院",
        "刚刚记入便签的重点嫌疑机构",
        "该重点嫌疑机构",
        "该重点嫌疑医院",
        "该医院",
        "这家医院",
        "排名第一的医疗机构",
        "排名第一的医院",
    )

    def apply(self, query: str, ctx: RewriteContext) -> RuleOutcome:
        if not any(kw in query for kw in self._SUSPECT_KEYWORDS):
            return RuleOutcome(query=query, matched=False)

        extractor = ctx.entity_extractor
        if extractor is None:
            from app.core.context.coreference_rewriter import ContextualQueryRewriter
            extractor = ContextualQueryRewriter.extract_top_entity_from_notes

        suspect = extractor(ctx.state)
        if not suspect and ctx.last_finding.get("key_entities"):
            suspect = ctx.last_finding["key_entities"][0]
        if not suspect:
            return RuleOutcome(query=query, matched=False)

        resolved = query
        for kw in self._SUSPECT_KEYWORDS:
            if kw in resolved:
                resolved = resolved.replace(kw, f"重点嫌疑机构『{suspect}』")
        logger.info(f"🔗 [CoreferenceRewriter] 绑定嫌疑机构实体『{suspect}』-> 「{resolved[:60]}...」")
        return RuleOutcome(query=resolved, matched=True, signal=SIGNAL_SUSPECT_BOUND, entities=(suspect,))


class _SceneSwitchSignalRule(_RewriteRule):
    """D3: 场景切换纯信号规则（不改写命题）。"""
    name = "scene_switch_signal"

    def apply(self, query: str, ctx: RewriteContext) -> RuleOutcome:
        if "切换核查场景" in query or "切换场景" in query:
            logger.info("🔀 [CoreferenceRewriter] 识别到明确场景切换指令，产出 scene_switch 信号供下游阻断历史继承。")
            return RuleOutcome(query=query, matched=True, signal=SIGNAL_SCENE_SWITCH)
        return RuleOutcome(query=query, matched=False)


class _CorrectionWrapRule(_RewriteRule):
    """D4: 口语反悔与参数纠偏 (In-Context Parameter Correction)。"""
    name = "correction_wrap"

    _CORRECTION_MARKERS: Tuple[str, ...] = (
        "不对", "改一下", "改成", "改用", "重新查", "算了",
        "太高了", "太少了", "加进来", "并进来", "一起算", "换成",
    )

    def apply(self, query: str, ctx: RewriteContext) -> RuleOutcome:
        if not any(kw in query for kw in self._CORRECTION_MARKERS):
            return RuleOutcome(query=query, matched=False)
        if not ctx.prev_resolved:
            return RuleOutcome(query=query, matched=False)
        clean_prev = re.sub(r"[？?。！!\s]+$", "", ctx.prev_resolved.strip())
        resolved = f"【用户纠偏指令：针对前序任务『{clean_prev}』，推翻旧条件并按最新口径重新执行】: {ctx.original_query}"
        logger.info(f"🔄 [CoreferenceRewriter] 识别到口语纠偏反悔 -> 「{resolved[:60]}...」")
        return RuleOutcome(query=resolved, matched=True, signal=SIGNAL_CORRECTION)


_REWRITE_PIPELINE: Tuple[_RewriteRule, ...] = (
    _AnaphoraExpansionRule(),
    _SuspectEntityRule(),
    _SceneSwitchSignalRule(),
    _CorrectionWrapRule(),
)


def _run_rewrite_pipeline(query: str, ctx: RewriteContext) -> Tuple[str, List[str], set, List[str]]:
    """按序执行改写规则，聚合 (最终命题, 生效规则名, 信号集, 实体增量)"""
    resolved = query
    matched_rules: List[str] = []
    signals: set = set()
    entities: List[str] = []
    for rule in _REWRITE_PIPELINE:
        outcome = rule.apply(resolved, ctx)
        if outcome.matched:
            matched_rules.append(rule.name)
            if outcome.signal:
                signals.add(outcome.signal)
            entities.extend(outcome.entities)
        resolved = outcome.query
    return resolved, matched_rules, signals, entities
