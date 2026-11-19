"""
app/core/scene_table_selector.py
=================================
[V2.0] 场景感知表选择器 — 自动根据用户查询选择正确的物理表

核心职责：
- 分析用户查询中的关键词
- 根据 scene_table_mapping 规则选择正确的表
- 返回目标表列表供 ContextBuilder 注入 Schema
- [V178.10] 自动拉入关联字典表（表间关联图谱）
- 生成强制性表选择提示语用于 Prompt 注入
"""

import re
from typing import List, Tuple, Optional
from loguru import logger
from app.core.registry.schema_registry import schema_registry
from app.core.schema.scene_match_evaluator import SceneMatchEvaluator, scene_match_evaluator
from app.core.schema.table_relation_linker import TableRelationLinker, table_relation_linker


class SceneTableSelector:
    """场景感知的物理表选择器"""

    FALLBACK_MAPPING = {
        "fqz_fymx_test": [
            "乡镇卫生院", "村卫生室", "门诊统筹", "批量刷单",
            "连续刷卡", "门诊费用", "牙", "拔牙",
            "口腔", "理疗", "康复", "卫生室", "卫生院",
            "门诊明细", "刷单", "门诊", "手术明细", "分解收费",
            "拆项目", "拆分", "主手术", "套账", "多记费用", "分解项目",
            "药品", "用药", "妇科", "专属", "耗材", "明细", "处方",
            "避孕", "节育", "上环", "冲正", "退费", "大额", "离群",
            "流水", "偏高", "超额"
        ],
        "fqz_gz_jzsj_all_ql": [
            "住院", "药店购药", "分解住院", "出院", "入院",
            "重叠住院", "压床", "住院天数", "药店", "定点药店",
            "就诊结算", "统筹基金", "对账", "反复结算", "拆单", "分解就诊",
            "就诊结算底表", "纯自费", "全额自费", "自费情况", "零自付"
        ],
        "fqz_cgzhan_hosp_fee": [
            "宏观费用", "月度费用", "机构费用统计", "医院费用统计", "月度统计",
            "定点医药机构宏观月度费用统计报表", "全库纳管", "期数", "总期数",
            "定点医药机构宏观", "宏观月度", "医药机构费用", "定点医药机构费用",
            "宏观资金汇总", "宏观资金", "宏观费用统计", "费用宏观", "机构费用报表", "timetype"
        ],
        "fqz_all_yy_yd": [
            "定点医疗机构", "定点零售药店", "医药机构", "医院名录",
            "药店名录", "二级医院", "三级医院", "定点医药机构", "纳管"
        ],
        "fqz_admdvs": [
            "行政区划", "区划字典", "层级划分", "国家级", "省级",
            "地市级", "区县级", "admdvs"
        ],
        "fqz_drug_mcs_info_list": [
            "目录库", "药品目录", "临床药品", "头孢", "哌拉西林",
            "抗感染", "抗生素品种", "收载"
        ]
    }

    def __init__(self, evaluator: Optional[SceneMatchEvaluator] = None, linker: Optional[TableRelationLinker] = None):
        self._evaluator = evaluator or scene_match_evaluator
        self._linker = linker or table_relation_linker
        self._mapping = self._load_mapping()
        self._relation_graph = self._load_relation_graph()

    def _load_mapping(self) -> dict:
        """从 schema_registry 加载场景映射并与 ArchetypeRegistry 领域知识库自动内聚融合"""
        mapping = {}
        try:
            entries = schema_registry.get_scene_table_mapping()
            for entry in entries:
                table = entry.get("table")
                scenes = entry.get("scenes", [])
                if table and scenes:
                    mapping[table] = list(scenes)
        except Exception as e:
            logger.warning(f"[SceneTableSelector] 加载失败，使用兜底映射: {e}")

        if not mapping:
            mapping = {k: list(v) for k, v in self.FALLBACK_MAPPING.items()}

        # 领域内聚 (Locality for Maintainers)：将 ArchetypeRegistry 的原型关键词注入对应物理表
        try:
            from app.core.registry.archetype_registry import archetype_registry
            for arch in archetype_registry._archetypes:
                for t in arch.target_tables:
                    if t not in mapping:
                        mapping[t] = []
                    for kw in arch.keywords:
                        if kw not in mapping[t]:
                            mapping[t].append(kw)
        except Exception as e:
            logger.debug(f"[SceneTableSelector] 注入原型关键词跳过: {e}")

        if mapping:
            logger.info(f"[SceneTableSelector] 加载场景映射: {len(mapping)} 表")
        return mapping

    def _load_relation_graph(self) -> dict:
        """从 schema_registry 加载表间关联图谱 (遵守公开接缝)"""
        try:
            graph = schema_registry.get_table_relation_graph()
            if graph:
                logger.info(f"[SceneTableSelector] 加载关联图谱: {len(graph)} 表")
            return graph
        except Exception as e:
            logger.debug(f"[SceneTableSelector] 关联图谱加载跳过: {e}")
            return {}

    def get_related_tables(self, primary_table: str, user_query: str) -> List[Tuple[str, str]]:
        """[V178.10 Deep Module] 根据主表和用户查询，返回需要拉入的关联表（委托至 TableRelationLinker 深模块）"""
        return self._linker.resolve_related_tables(
            primary_table=primary_table,
            user_query=user_query,
            relation_graph=self._relation_graph,
        )

    def select_tables(self, user_query: str) -> Tuple[str, List[str]]:
        """[V2.0 Deep Module] 根据用户查询选择目标表，返回 (primary_table, all_tables)"""
        scores = self._evaluator.evaluate(user_query, self._mapping)

        if not scores:
            primary = schema_registry.get_main_table()
            logger.info(f"[SceneTableSelector] 无场景匹配，使用默认主表: {primary}")
            return primary, [primary]

        primary = max(scores, key=scores.get)
        all_tables = list(scores.keys())

        # [V178.10] 检查关联图谱，自动拉入字典表
        related = self.get_related_tables(primary, user_query)
        for table_name, _ in related:
            if table_name not in all_tables:
                all_tables.append(table_name)
                logger.info(f"[SceneTableSelector] 关联表拉入: {table_name}")

        logger.info(f"[SceneTableSelector] 场景匹配: 主表={primary}, 表={all_tables}, 分={scores}")
        return primary, all_tables

    def get_enforcement_hint(self, user_query: str) -> Optional[str]:
        """
        [Matt Pocock Deep Module] 
        生成综合物理表选择与领域原型强约束提示语，委托至 table_guideline_renderer 深模块。
        """
        primary, _ = self.select_tables(user_query)
        from app.core.planning.table_guideline_renderer import render_table_guidelines
        return render_table_guidelines(primary, user_query)


# 模块级单例
scene_table_selector = SceneTableSelector()
