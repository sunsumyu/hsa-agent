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

class ModelTier(str, Enum):
    LIGHT = "LIGHT"  # 快速、低成本模型 (e.g. 7B, 8B, Lite)
    HEAVY = "HEAVY"  # 高智能、高成本模型 (e.g. V3, GPT-4, Gemini-Pro)


@dataclass
class RouteResult:
    """路由决策结果"""
    route_type: RouteType
    target_id: str              # 对应的算子 ID（如 "GENDER_CONFLICT"）
    confidence: float           # 置信度 [0.0, 1.0]
    matched_keywords: List[str] = field(default_factory=list)
    extra_filters: Dict[str, str] = field(default_factory=dict)
    model_tier: ModelTier = ModelTier.HEAVY # [V167.0] 默认使用强力模型
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
        "target_id": "CONTACT_SHARING",
        "route_type": RouteType.KNOWN_RULE,
        "exact_keywords": ["联系方式共用", "共用电话", "电话相同", "共用手机号"],
        "fuzzy_groups": [
            ["患者", "职工", "共用"],
            ["手机号", "相同"],
            ["联系电话", "共用"],
        ],
        "description": "患者与职工共用联系方式检测",
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
            rule_config: 自定义规则配置列表。不传则按以下优先级加载:
                1. configs/routing_rules.yaml (推荐, 可热更新)
                2. DEFAULT_RULE_CONFIG (fallback 硬编码)
                可传入空列表禁用所有快速路由（纯 LLM 模式）。
        """
        if rule_config is not None:
            self._config = rule_config
            return

        # 优先从 YAML 注册表加载
        try:
            from app.core.rule_registry import rule_registry
            yaml_rules = rule_registry.routing_rules.get_rules_as_dicts()
            if yaml_rules:
                # 归一化 route_type 为枚举值 (YAML 存字符串)
                for r in yaml_rules:
                    rt = r.get("route_type", "KNOWN_RULE")
                    if isinstance(rt, str):
                        try:
                            r["route_type"] = RouteType(rt)
                        except ValueError:
                            r["route_type"] = RouteType.UNKNOWN
                self._config = yaml_rules
                return
        except Exception as e:
            from loguru import logger
            logger.warning(f"[FastRouter] YAML rules load failed, fallback to hardcoded: {e}")

        self._config = DEFAULT_RULE_CONFIG

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
        
        # 提取动态参数（如：尾号 8888）
        import re
        extra_filters = {}
        tail_match = re.search(r"尾号\s*(\d{3,11})", text)
        if tail_match:
            extra_filters["tel"] = f"LIKE '%{tail_match.group(1)}'"
        
        amt_match = re.search(r"金额\s*[>|超过]\s*(\d+)", text)
        if amt_match:
            extra_filters["medfee_sumamt"] = f"> {amt_match.group(1)}"

        # 优先级 1：精确关键词匹配（置信度 1.0）
        result = self._match_exact(text, extra_filters)
        if result:
            return result

        # 优先级 2：模糊关键词组合匹配（置信度 0.7~0.95）
        result = self._match_fuzzy(text, extra_filters)
        if result:
            return result

        # 优先级 3：未知类型，根据复杂度进行模型分级 (V167.0)
        tier = self._estimate_complexity(text)
        return RouteResult(
            route_type=RouteType.UNKNOWN,
            target_id="",
            confidence=0.0,
            model_tier=tier,
            reason=f"未匹配到任何已知规则，评估复杂度级别为: {tier}",
        )

    def _estimate_complexity(self, text: str) -> ModelTier:
        """
        [V167.0] 复杂度评估器：识别高维分析需求。
        """
        # 简单查询特征词
        light_patterns = ["解释", "定义", "是谁", "查一下", "多少钱"]
        # 复杂分析特征词
        heavy_patterns = ["趋势", "分布", "关联", "对比", "同环比", "异动", "交叉", "特征", "聚集", "偏离"]
        
        if any(p in text for p in heavy_patterns) or len(text) > 60:
            return ModelTier.HEAVY
        
        # 如果包含大量“解释”类词汇且长度较短，设为 LIGHT
        if any(p in text for p in light_patterns):
            return ModelTier.LIGHT
            
        return ModelTier.HEAVY # 默认安全起见使用 HEAVY

    def get_all_rules(self) -> List[Dict]:
        """返回当前所有路由规则配置（用于调试和展示）"""
        return list(self._config)

    # ──────────────────────────────────────────────────────
    # 内部匹配逻辑
    # ──────────────────────────────────────────────────────

    def _match_exact(self, text: str, extra_filters: Dict[str, str]) -> Optional[RouteResult]:
        """精确关键词匹配"""
        for rule in self._config:
            for kw in rule.get("exact_keywords", []):
                if kw in text:
                    return RouteResult(
                        route_type=rule["route_type"],
                        target_id=rule["target_id"],
                        confidence=1.0,
                        matched_keywords=[kw],
                        extra_filters=extra_filters,
                        reason=f"精确匹配关键词「{kw}」→ {rule['description']}",
                    )
        return None

    def _match_fuzzy(self, text: str, extra_filters: Dict[str, str]) -> Optional[RouteResult]:
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
                        extra_filters=extra_filters,
                        reason=f"模糊匹配组合 {matched} → {rule['description']}",
                    )
                    if best is None or confidence > best[0]:
                        best = (confidence, result)

        return best[1] if best else None


# 模块级单例（供 agent_graph 直接使用）
fast_router = FastAuditRouter()
