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


class SceneTableSelector:
    """场景感知的物理表选择器"""

    FALLBACK_MAPPING = {
        "fqz_fymx_test": [
            "乡镇卫生院", "村卫生室", "门诊统筹", "批量刷单",
            "连续刷卡", "QA-CUST-26", "门诊费用", "牙", "拔牙",
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
            "就诊结算", "统筹基金", "对账", "反复结算", "拆单", "分解就诊"
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

    def __init__(self):
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
        """[V178.10] 根据主表和用户查询，返回需要拉入的关联表。"""
        if not self._relation_graph or primary_table not in self._relation_graph:
            return []
        graph_entry = self._relation_graph[primary_table]
        auto_pull = graph_entry.get("auto_pull", [])
        query_lower = user_query.lower()
        related = []
        for entry in auto_pull:
            table = entry.get("table", "")
            keywords = entry.get("pull_keywords", [])
            hint = entry.get("hint", "")
            if any(kw.lower() in query_lower for kw in keywords):
                related.append((table, hint))
                logger.info(f"[SceneTableSelector] 关联表命中: {table}")
        return related

    def select_tables(self, user_query: str) -> Tuple[str, List[str]]:
        """根据用户查询选择目标表，返回 (primary_table, all_tables)"""
        query_lower = user_query.lower()
        scores = {}
        for table, keywords in self._mapping.items():
            score = sum(1 for kw in keywords if kw.lower() in query_lower)
            if table.lower() in query_lower:
                score += 50  # 显式指定物理表名，拥有绝对优先权 (Matt Pocock Deep Module Invariance)
            if score > 0:
                scores[table] = score


        # 结合 ArchetypeRegistry 领域原型增强匹配加权
        from app.core.registry.archetype_registry import archetype_registry
        for arch in archetype_registry.match_archetypes(query_lower):
            for t in arch.target_tables:
                scores[t] = scores.get(t, 0) + 2

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
        生成综合物理表选择与领域原型强约束提示语，用于 Prompt 注入 (Matt Pocock Deep Module)
        """
        primary, _ = self.select_tables(user_query)
        table_hint = None
        if primary == "fqz_fymx_test":
            table_hint = """
【⚠️ 物理表选择指引 (TABLE SELECTION HINT)】
根据场景关键词检测，建议使用 `fqz_fymx_test` 表。

理由：
1. 乡镇卫生院/村卫生室/门诊统筹场景的费用数据存储在 `fqz_fymx_test`
2. `fqz_fymx_test.fixmedins_name` 是真实中文机构名，可 LIKE 匹配
3. `fqz_gz_jzsj_all_ql.fixmedins_name` 是加密混淆字段，无法中文匹配
4. 两表 setl_id 完全不重叠，JOIN 会导致数据丢失

字段注意事项：
- `fqz_fymx_test.setl_time` 是 String 类型且尾部带 \\t，**严禁**直接 toDateTime()，必须用 toDateTime(substring(trim(setl_time),1,19)) 转换
- 必须用 trim(...) 清理字符串字段
- med_type 编码：11=门诊统筹，21=住院，53_04=特病门诊

注意：以上仅为表选择指引，SQL 查询模式请根据审计方法论和用户原始问题自行决定，不要照搬历史 SQL 模板。
"""
        elif primary == "fqz_all_yy_yd":
            table_hint = """
【⚠️ 物理表选择指引 (TABLE SELECTION HINT)】
当前审计任务涉及医疗机构/药店名录普查与统计，物理主表为 `fqz_all_yy_yd`。
机构代码为 `fixmedins_code`，机构名称为 `fixmedins_name`，机构类型为 `medins_type`，有效标志为 `vali_flag`。
严禁使用 `yyjg_zzml`、`medical_institutions` 等任何虚构表名！必须直接在 `fqz_all_yy_yd` 上执行 SQL 统计！
"""
        elif primary == "fqz_admdvs":
            table_hint = """
【⚠️ 物理表选择指引 (TABLE SELECTION HINT)】
当前任务涉及医保行政区划字典与层级，物理主表为 `fqz_admdvs`。
真实物理字段如下：
- 区划代码为 `admdvs`
- 区划名称为 `admdvs_name`
- 区划层级为 `admdvs_lv`（1=国家级, 2=省级, 3=市级, 4=区县级）
- 上级区划代码为 `prnt_admdvs`
严禁探查 system.tables 或捏造外部表名！直接在 `fqz_admdvs` 上按 `admdvs_lv` 分组统计即可。
"""
        elif primary == "fqz_drug_mcs_info_list":
            table_hint = """
【⚠️ 物理表选择指引 (TABLE SELECTION HINT)】
当前任务涉及医保药品目录与药品特征分类，物理主表为 `fqz_drug_mcs_info_list`。
药品代码为 `med_list_code`，药品通用名/商品名为 `drug_prodname` / `genname_codg`。
"""

        # 结合 ArchetypeRegistry 领域任务原型的不变式约束 (Locality & Leverage)
        from app.core.registry.archetype_registry import archetype_registry
        archetype_hints = []
        for arch in archetype_registry.match_archetypes(user_query):
            if arch.enforcement_hint:
                archetype_hints.append(f"【🚨 {arch.display_name}结构守卫】\n{arch.enforcement_hint}")

        if not table_hint and not archetype_hints:
            return None

        parts = []
        if table_hint:
            parts.append(table_hint.strip())
        if archetype_hints:
            parts.append("\n\n".join(archetype_hints))

        return "\n\n".join(parts)


# 模块级单例
scene_table_selector = SceneTableSelector()
