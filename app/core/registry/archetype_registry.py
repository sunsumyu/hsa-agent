"""
app/core/registry/archetype_registry.py
======================================
[V220.0] 领域任务原型注册中心 (Audit Archetype Registry)

统一解决 Fowler 代码坏味道 "Shotgun Surgery" (霰弹式修改)：
消除业务场景、审计原型在 gates.py, scene_table_selector.py, query_classifier.py, fast_router.py
等多个模块中的关键词碎片化硬编码。

对外提供清晰、高杠杆的深模块接口：
- ArchetypeRegistry.match_archetypes(query: str) -> List[AuditArchetype]
- ArchetypeRegistry.get_primary_archetype(query: str) -> Optional[AuditArchetype]
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Tuple
from loguru import logger


class ArchetypeCategory(str, Enum):
    RECONCILIATION = "reconciliation"          # 资金对账 / 日结 / 费用守恒
    INVENTORY = "inventory"                    # 字典盘点 / 名录统计 / 行政区划层级
    RANKING = "ranking"                        # 排名 / TOP-N / 离群极值
    GENDER_CONFLICT = "gender_conflict"        # 性别限制冲突
    CLINICAL_CATALOG = "clinical_catalog"      # 药品 / 诊疗目录核查
    MISSING_COMPANION = "missing_companion"    # 伴随依赖缺失核查 (如无手术收麻醉)
    TEMPORAL_OVERLAP = "temporal_overlap"      # 时序冲突 / 重叠住院
    REVERSAL_REFUND = "reversal_refund"        # 退费与冲正流水核查
    SPLIT_BILLING = "split_billing"            # 分解收费 / 套收 / 拆开计费
    DRUG_RESALE = "drug_resale"                # 药贩子套现 / 高频异常购药网络
    GENERAL_AUDIT = "general_audit"            # 常规结算稽核


@dataclass(frozen=True)
class AuditArchetype:
    """领域任务原型值对象 (Value Object)"""
    category: ArchetypeCategory
    name: str
    display_name: str
    keywords: Tuple[str, ...]
    target_tables: Tuple[str, ...] = field(default_factory=tuple)
    requires_group_by: bool = False
    forbid_raw_limit: bool = False
    enforcement_hint: Optional[str] = None

    def match_score(self, query: str) -> int:
        """返回匹配度得分 (命中关键词数量)"""
        q = query.lower()
        return sum(1 for kw in self.keywords if kw.lower() in q)


class ArchetypeRegistry:
    """任务原型注册中心 (Deep Module)"""

    _DEFAULT_ARCHETYPES: List[AuditArchetype] = [
        AuditArchetype(
            category=ArchetypeCategory.RECONCILIATION,
            name="reconciliation",
            display_name="资金对账与宏观汇总",
            keywords=(
                "对账", "资金对账", "日结", "月结", "按不同的结算日期",
                "日度", "年度结算", "结算的总体情况", "费用守恒", "结算对账", "差异"
            ),
            target_tables=("fqz_gz_jzsj_all_ql",),
            requires_group_by=True,
            forbid_raw_limit=True,
            enforcement_hint=(
                "本任务为【资金对账与宏观汇总】任务，必须使用 GROUP BY 按时间/机构等业务维度进行全量聚合统计，"
                "严禁对明细流水直接施加 LIMIT 截断或采样！请直接按维度聚合输出完整统计数据。"
            ),
        ),
        AuditArchetype(
            category=ArchetypeCategory.INVENTORY,
            name="inventory",
            display_name="层级分布/名录盘点",
            keywords=(
                "层级划分", "各有多少个", "四级", "名录库", "收载了多少种",
                "各有多少个品种", "有多少家", "定点医疗机构", "定点零售药店",
                "医药机构", "医院名录", "药店名录", "二级医院", "三级医院"
            ),
            target_tables=("fqz_all_yy_yd", "fqz_admdvs", "fqz_drug_mcs_info_list"),
            requires_group_by=True,
            forbid_raw_limit=True,
            enforcement_hint=(
                "本任务为【层级分布/名录盘点】统计任务，必须使用 GROUP BY（如 GROUP BY admdvs_lv / medins_type）"
                "进行全量分类汇总，严禁施加 LIMIT 采样明细！"
            ),
        ),
        AuditArchetype(
            category=ArchetypeCategory.GENDER_CONFLICT,
            name="gender_conflict",
            display_name="性别限制冲突",
            keywords=(
                "性别限制", "男性", "女性", "妇科", "前列腺",
                "避孕", "节育", "上环", "子宫", "卵巢"
            ),
            target_tables=("fqz_fymx_test",),
            requires_group_by=False,
            forbid_raw_limit=False,
            enforcement_hint="性别限制冲突核查任务：需关联费用明细表 fqz_fymx_test 筛选性别与专属药品/耗材对碰。",
        ),
        AuditArchetype(
            category=ArchetypeCategory.CLINICAL_CATALOG,
            name="clinical_catalog",
            display_name="药品与耗材目录核查",
            keywords=(
                "目录库", "药品目录", "耗材目录", "医保目录", "三大目录",
                "生产厂家", "剂型", "规格", "国家医保编码", "抗感染",
                "抗生素品种", "头孢", "哌拉西林", "收载"
            ),
            target_tables=("fqz_drug_mcs_info_list",),
            requires_group_by=False,
            forbid_raw_limit=False,
            enforcement_hint="目录库核查任务：需使用国家药品与诊疗耗材目录库 fqz_drug_mcs_info_list。",
        ),
        AuditArchetype(
            category=ArchetypeCategory.RANKING,
            name="ranking",
            display_name="排名与极值核查",
            keywords=(
                "排名", "最高", "前", "top", "从高到低", "从低到高", "排序"
            ),
            target_tables=(),
            requires_group_by=False,
            forbid_raw_limit=False,
            enforcement_hint=None,
        ),
        AuditArchetype(
            category=ArchetypeCategory.MISSING_COMPANION,
            name="missing_companion",
            display_name="伴随依赖缺失核查",
            keywords=(
                "无手术", "未做手术", "未收取手术", "无手术收取麻醉",
                "麻醉费", "麻醉", "全麻", "局麻", "伴随缺失", "前置缺失",
                "未做化验", "未做检查", "缺少前提"
            ),
            target_tables=("fqz_fymx_test",),
            requires_group_by=False,
            forbid_raw_limit=False,
            enforcement_hint=(
                "本任务为【伴随依赖缺失核查】任务（如计收麻醉但无手术），"
                "必须在就诊/结算粒度通过子查询 (`NOT IN / NOT EXISTS`) 或 `LEFT JOIN ... IS NULL` 跨行核对前提项目的存在性，"
                "严禁在单条明细的 WHERE 子句中直接施加伴随字段的否定排除！"
            ),
        ),
        AuditArchetype(
            category=ArchetypeCategory.TEMPORAL_OVERLAP,
            name="temporal_overlap",
            display_name="时序冲突与重叠住院",
            keywords=(
                "同时住院", "重叠住院", "异地同时", "同一天内", "两家不同医院",
                "入出院时序", "入院时间晚于出院", "时间倒置", "跨院同时"
            ),
            target_tables=("fqz_gz_jzsj_all_ql", "fqz_all_yy_yd_1"),
            requires_group_by=False,
            forbid_raw_limit=False,
            enforcement_hint=(
                "本任务为【时序冲突与重叠住院】任务，必须对同一参保人 (`psn_no`) 跨机构记录进行自连接区间重叠计算，"
                "或比对入院出院时间 (`start_date > end_date`)。"
            ),
        ),
        AuditArchetype(
            category=ArchetypeCategory.REVERSAL_REFUND,
            name="reversal_refund",
            display_name="退费与冲正流水核查",
            keywords=(
                "退费", "冲正", "负数金额", "异常退费", "冲正流水", "负数退费"
            ),
            target_tables=("fqz_fymx_test",),
            requires_group_by=False,
            forbid_raw_limit=False,
            enforcement_hint="退费与冲正核查：必须路由至明细表 fqz_fymx_test 筛选 det_item_fee_sumamt < 0。",
        ),
        AuditArchetype(
            category=ArchetypeCategory.SPLIT_BILLING,
            name="split_billing",
            display_name="手术分解与套收计费核查",
            keywords=(
                "分解收费", "拆分收费", "手术分解", "套收", "拆开计费",
                "主干手术与子步骤", "分解项目", "拆单"
            ),
            target_tables=("fqz_fymx_test",),
            requires_group_by=False,
            forbid_raw_limit=False,
            enforcement_hint=(
                "本任务为【手术分解与套收计费核查】任务（如主干手术与子步骤拆分计费），"
                "必须在同就诊/结算（setl_id 或 mdtrt_id）粒度通过自连接 JOIN 或分组计数进行联合核对，"
                "严禁在单条明细记录的 WHERE 条件中施加互相冲突的等值条件！"
            ),
        ),
        AuditArchetype(
            category=ArchetypeCategory.DRUG_RESALE,
            name="drug_resale",
            display_name="药贩子套现与频繁异常购药网络",
            keywords=(
                "药贩子", "倒药", "套现", "频繁购药", "异常购药", "超量购药",
                "门诊慢特病购药", "闭环套现", "跨机构购药", "高频次异常购药"
            ),
            target_tables=("fqz_gz_jzsj_all_ql", "fqz_fymx_test"),
            requires_group_by=True,
            forbid_raw_limit=True,
            enforcement_hint=(
                "本任务为【药贩子套现与频繁异常购药网络】任务，违规行为体现为跨机构高频开药或定点闭环。"
                "必须按参保人（GROUP BY psn_no 或 psn_no, toDate(setl_time)）进行全量聚合统计，"
                "严禁对明细流水直接施加 LIMIT 采样，亦不可在单条明细上仅按 cnt > 100 进行单条过滤！"
            ),
        ),
    ]

    def __init__(self, archetypes: Optional[List[AuditArchetype]] = None):
        self._archetypes = archetypes or self._DEFAULT_ARCHETYPES.copy()

    def match_archetypes(self, query: str) -> List[AuditArchetype]:
        """根据查询文本返回所有命中的任务原型，按匹配得分降序排序。"""
        if not query:
            return []
        scored = []
        for arch in self._archetypes:
            score = arch.match_score(query)
            if score > 0:
                scored.append((score, arch))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [arch for _, arch in scored]

    def get_primary_archetype(self, query: str) -> Optional[AuditArchetype]:
        """返回最高置信度的主任务原型。"""
        matched = self.match_archetypes(query)
        return matched[0] if matched else None


archetype_registry = ArchetypeRegistry()
