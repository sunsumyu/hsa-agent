"""
app/skills/rule_catalog.py
==========================
[SPEC-227 / Matt Pocock Deep Module / Facade] 医保审计规则目录与方法论门面 (Rule Catalog)

职责：
- 规则语义名称/别名到标准 Target ID 的多源消解 (委托至 RulePatternResolver)
- 行业审计专家公认的方法论、判定标准与法律依据 (ICD-10, 监督管理条例, 处方管理办法)
- 物理执行容差阈值计算 (委托至 RuleTolerancePolicy)
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple
from app.skills.rule_pattern_resolver import rule_pattern_resolver, RulePatternResolver
from app.skills.rule_tolerance_policy import rule_tolerance_policy, RuleTolerancePolicy


class RuleCatalog:
    """审计规则目录与方法论门面"""

    # 别名与模糊特征映射表 (向后兼容暴露类属性)
    _PATTERNS: Tuple[Tuple[str, str], ...] = RulePatternResolver.DEFAULT_PATTERNS

    # 权威审计方法论与合规法规依据知识库
    RULE_METADATA: Dict[str, str] = {
        "GENDER_CONFLICT": (
            "【审计方法论】性别冲突校验：严格摒弃关键字模糊匹配。必须通过 JOIN 医保三大目录 (med_catalog)，"
            "利用国家标准的 gender_limit = 'Female' 字段进行精准对撞。"
            "合规依据：《疾病分类与代码国家临床版(ICD-10)》及《医疗保障基金使用监督管理条例》第十五条。"
        ),
        "HIGH_FREQ_DRUG_PURCHASE": (
            "【审计方法论】高频购药核查：按 psn_no 执行窗口聚合。"
            "判定标准：自然月内同一药品购药频次 > 4次 或 累计剂量超过临床用药指南 200%。"
            "合规依据：《处方管理办法》及医保限额规定。"
        ),
        "DECOMPOSITION_HOSPITALIZATION": (
            "【审计方法论】分解住院侦测：通过窗口函数 (Window Function) 对比相邻住院记录。"
            "判定标准：同一患者出院与下次入院间隔时间 <= 15天 且 诊断高度相关。"
            "合规依据：《基本医疗保险定点医疗机构服务协议》关于禁止恶意分解住院的条款。"
        ),
        "CROSS_HOSPITAL_OVERLAP": (
            "【审计方法论】跨机构重复住院核查：执行时间区间交集运算。"
            "判定标准：(A.start <= B.end) AND (A.end >= B.start) 且机构编码不一致。"
            "合规依据：医保实时结算管理规定，严禁“同时住院”挂账。"
        ),
        "REPEAT_BILLING_DETECTOR": (
            "【审计方法论】重复收费校验：对单次就诊 (setl_id) 执行项目级明细扫描。"
            "判定标准：同一项目 (item_code) 的实收数量超过单日限额或物理操作逻辑上线。"
            "合规依据：《医疗服务价格目录》。"
        ),
        "CONTACT_SHARING_DETECTOR": (
            "【联邦分治强制令】针对团伙作案/共用手机号任务，严禁使用单库SQL！必须执行三阶段："
            "Phase 1: 使用 federated_graph_sideloader 执行 Cypher (例如 MATCH (p:Patient)-[:HAS_PHONE]->(pn:Phone) WHERE pn.number ENDS WITH '8888'...)；"
            "Phase 2: 根据返回的临时表名，使用 execute_audit_sql 执行 JOIN 汇总业务总额；"
            "Phase 3: 提取全院基线，使用 Python 或手动计算真正的统计学阈值。"
        ),
        "VIX_ANOMALY_SCAN": (
            "【审计方法论】VIX 变异指数扫描：采用统计学离群值分析。"
            "判定标准：机构均次费用变异系数 (CV) 超过总体均值 3 个标准差。"
            "合规依据：医保基金运行监测风险预警指标体系。"
        ),
        "CLUSTER_ENCOUNTER_DETECTOR": (
            "【审计方法论】聚集就医图谱挖掘：基于 Neo4j 执行连通分量分析。"
            "判定标准：核心节点（医生/药店/手机号）关联的参保人分布密度达到异常阈值。"
            "合规依据：医保大数据反欺诈模型规范。"
        ),
    }

    def __init__(
        self,
        resolver: Optional[RulePatternResolver] = None,
        tolerance_policy: Optional[RuleTolerancePolicy] = None,
    ):
        self._resolver = resolver or rule_pattern_resolver
        self._tolerance_policy = tolerance_policy or rule_tolerance_policy

    def resolve_target_id(self, rule_id: str) -> str:
        """从输入的规则语义词或英文缩写解析标准规则 Target ID"""
        return self._resolver.resolve(rule_id)

    def get_methodology(self, target_id: str) -> str:
        """获取规则权威审计方法论"""
        return self.RULE_METADATA.get(target_id, "自定义规则逻辑匹配")

    def get_tolerance(self, target_id: str) -> int:
        """获取明细级业务容差阈值"""
        return self._tolerance_policy.compute_tolerance(target_id)


rule_catalog = RuleCatalog()
