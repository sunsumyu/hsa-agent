"""
app/fast_router.py
==================
[企业级可复用模块] 快速规则路由器

解决问题：
    Vellum/Anthropic 研究表明：对于已知类型的结构化任务（如审计规则匹配），
    使用 LLM 去生成 SQL 是一种极度浪费——它不仅耗时，还引入了幻觉风险。
    "Fast Route" 思想：在任务进入 LLM 推理链之前，先判断是否属于"已知规则类"，
    如果是，直接映射到确定性算子，完全跳过 LLM。

设计原则：
    - 零业务依赖：路由规则通过配置而非硬编码定义
    - 可扩展：新增业务规则只需修改规则配置，无需改代码
    - 可测试：所有路由逻辑均可独立单元测试
    - 透明：路由结果包含置信度和匹配依据，便于调试

路由策略：
    优先级 1: 精确关键词匹配（最高置信度）
    优先级 2: 模糊关键词组合匹配
    优先级 3: 默认降级到 LLM 推理（UNKNOWN 类型）

使用方式：
    from app.fast_router import FastAuditRouter, RouteType

    router = FastAuditRouter()
    result = router.classify("核查中心医院是否存在患者与职工共用联系方式？")

    if result.route_type == RouteType.KNOWN_RULE:
        # 直接走规则算子，跳过 LLM
        sql = rule_engine.get_rule_sql(result.target_id)
    elif result.route_type == RouteType.KNOWN_ALGO:
        # 直接走异常检测算法
        sql = anomaly_detector.get_algorithm_sql(result.target_id)
    else:
        # 未知类型，需要 LLM 推理
        pass
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Tuple


class RouteType(str, Enum):
    KNOWN_RULE = "KNOWN_RULE"    # 已知审计规则 → 直接调用 rule_engine
    KNOWN_ALGO = "KNOWN_ALGO"    # 已知异常算法 → 直接调用 anomaly_detector
    UNKNOWN = "UNKNOWN"          # 未知类型 → 需要 LLM 推理


@dataclass
class RouteResult:
    """路由决策结果"""
    route_type: RouteType
    target_id: str              # 对应的算子 ID（如 "GENDER_CONFLICT"）
    confidence: float           # 置信度 [0.0, 1.0]
    matched_keywords: List[str] = field(default_factory=list)
    reason: str = ""


# ──────────────────────────────────────────────────────────
# 默认规则路由配置
# 可在实例化时通过 rule_config 参数完全替换
# ──────────────────────────────────────────────────────────
DEFAULT_RULE_CONFIG: List[Dict] = [
    {
        "target_id": "GENDER_CONFLICT",
        "route_type": RouteType.KNOWN_RULE,
        "exact_keywords": ["性别冲突", "性别不符", "男性妇科", "女性男科"],
        "fuzzy_groups": [
            ["性别", "诊断"],
            ["男", "妇科"],
            ["女", "前列腺"],
            ["男", "子宫"],
            ["男", "乳腺"],
        ],
        "description": "性别与诊断不符检测",
    },
    {
        "target_id": "CROSS_HOSPITAL_OVERLAP",
        "route_type": RouteType.KNOWN_RULE,
        "exact_keywords": ["重复住院", "跨院重复", "同时住院", "双院住院"],
        "fuzzy_groups": [
            ["同一患者", "两家医院"],
            ["重复", "住院"],
            ["跨机构", "住院"],
            ["同期", "住院"],
        ],
        "description": "跨机构重复住院检测",
    },
    {
        "target_id": "DECOMPOSITION_HOSPITALIZATION",
        "route_type": RouteType.KNOWN_RULE,
        "exact_keywords": ["分解住院", "住院分解", "短期再入院"],
        "fuzzy_groups": [
            ["出院", "再次入院", "短期"],
            ["分解", "住院"],
            ["间隔", "天", "再住院"],
        ],
        "description": "分解住院检测（短期内二次入院）",
    },
    {
        "target_id": "HIGH_FREQ_DRUG_PURCHASE",
        "route_type": RouteType.KNOWN_RULE,
        "exact_keywords": ["高频购药", "频繁购药", "大量购药"],
        "fuzzy_groups": [
            ["购药", "频率"],
            ["药店", "多次"],
            ["购药", "异常"],
        ],
        "description": "高频购药异常检测",
    },
    {
        "target_id": "REPEAT_BILLING_DETECTOR",
        "route_type": RouteType.KNOWN_RULE,
        "exact_keywords": ["重复收费", "重复结算", "多次收取"],
        "fuzzy_groups": [
            ["同一天", "同一患者", "多次"],
            ["同一医院", "重复", "费用"],
            ["重复", "结算", "同一"],
            ["同一天", "重复", "收费"],
        ],
        "description": "同日同迺同容重复收费检测",
    },
    {
        "target_id": "CONTACT_SHARING_DETECTOR",
        "route_type": RouteType.KNOWN_RULE,
        "exact_keywords": ["共用联系方式", "联系方式共用", "共用手机号", "尾号异常"],
        "fuzzy_groups": [
            ["联系方式", "异常", "报销"],
            ["手机号", "共用", "患者"],
            ["联系方式", "负责人", "报销"],
            ["联系", "尾号", "异常偏高"],
        ],
        "description": "共用联系方式 + 报销金额异常偏高欺诈检测",
    },
    {
        "target_id": "VIX_ANOMALY_SCAN",
        "route_type": RouteType.KNOWN_ALGO,
        "exact_keywords": ["变异指数", "VIX", "机构变异"],
        "fuzzy_groups": [
            ["机构", "异常", "费用"],
            ["医院", "变异"],
        ],
        "description": "医疗机构费用变异指数扫描",
    },
    {
        "target_id": "STATISTICAL_OUTLIER_DETECTOR",
        "route_type": RouteType.KNOWN_ALGO,
        "exact_keywords": ["离群", "异常高消费", "统计异常"],
        "fuzzy_groups": [
            ["消费", "异常", "偏高"],
            ["统计", "离群"],
            ["报销", "异常偏高"],
        ],
        "description": "统计学离群点检测",
    },
    {
        "target_id": "CLUSTER_ENCOUNTER_DETECTOR",
        "route_type": RouteType.KNOWN_ALGO,
        "exact_keywords": ["聚集就医", "欺诈网络"],
        "fuzzy_groups": [
            ["聚集", "患者"],
            ["成群", "就医"],
        ],
        "description": "聚集性就医欺诈网络检测",
    },
]


class FastAuditRouter:
    """
    快速审计任务路由器。

    在任务进入 LLM 推理链之前，先判断是否可以直接映射到已知确定性算子，
    从而跳过 LLM 调用，大幅降低延迟和 Token 成本。
    """

    def __init__(self, rule_config: Optional[List[Dict]] = None):
        """
        Args:
            rule_config: 自定义规则配置列表。不传则使用默认配置。
                         可传入空列表禁用所有快速路由（纯 LLM 模式）。
        """
        self._config = rule_config if rule_config is not None else DEFAULT_RULE_CONFIG

    def classify(self, user_question: str) -> RouteResult:
        """
        对用户问题进行路由分类。

        Args:
            user_question: 用户输入的审计任务描述

        Returns:
            RouteResult，包含路由类型、目标算子 ID 和置信度
        """
        if not user_question or not user_question.strip():
            return RouteResult(
                route_type=RouteType.UNKNOWN,
                target_id="",
                confidence=0.0,
                reason="问题为空",
            )

        text = user_question.strip()

        # 优先级 1：精确关键词匹配（置信度 1.0）
        result = self._match_exact(text)
        if result:
            return result

        # 优先级 2：模糊关键词组合匹配（置信度 0.7~0.95）
        result = self._match_fuzzy(text)
        if result:
            return result

        # 优先级 3：未知类型，需要 LLM 推理
        return RouteResult(
            route_type=RouteType.UNKNOWN,
            target_id="",
            confidence=0.0,
            reason="未匹配到任何已知规则，需要 LLM 推理",
        )

    def get_all_rules(self) -> List[Dict]:
        """返回当前所有路由规则配置（用于调试和展示）"""
        return list(self._config)

    # ──────────────────────────────────────────────────────
    # 内部匹配逻辑
    # ──────────────────────────────────────────────────────

    def _match_exact(self, text: str) -> Optional[RouteResult]:
        """精确关键词匹配"""
        for rule in self._config:
            for kw in rule.get("exact_keywords", []):
                if kw in text:
                    return RouteResult(
                        route_type=rule["route_type"],
                        target_id=rule["target_id"],
                        confidence=1.0,
                        matched_keywords=[kw],
                        reason=f"精确匹配关键词「{kw}」→ {rule['description']}",
                    )
        return None

    def _match_fuzzy(self, text: str) -> Optional[RouteResult]:
        """模糊关键词组合匹配，找出最高置信度的规则"""
        best: Optional[Tuple[float, RouteResult]] = None

        for rule in self._config:
            for group in rule.get("fuzzy_groups", []):
                matched = [kw for kw in group if kw in text]
                if len(matched) == len(group):
                    # 所有关键词都命中
                    confidence = round(0.7 + 0.05 * (len(group) - 1), 2)
                    confidence = min(confidence, 0.95)
                    result = RouteResult(
                        route_type=rule["route_type"],
                        target_id=rule["target_id"],
                        confidence=confidence,
                        matched_keywords=matched,
                        reason=f"模糊匹配组合 {matched} → {rule['description']}",
                    )
                    if best is None or confidence > best[0]:
                        best = (confidence, result)

        return best[1] if best else None


# 模块级单例（供 agent_graph 直接使用）
fast_router = FastAuditRouter()
