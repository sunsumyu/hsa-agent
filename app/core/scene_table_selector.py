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
            "门诊明细", "刷单", "门诊"
        ],
        "fqz_gz_jzsj_all_ql": [
            "住院", "药店购药", "分解住院", "出院", "入院",
            "重叠住院", "压床", "住院天数", "药店", "定点药店"
        ]
    }

    def __init__(self):
        self._mapping = self._load_mapping()
        self._relation_graph = self._load_relation_graph()

    def _load_mapping(self) -> dict:
        """从 schema_registry.yaml 加载场景映射"""
        try:
            config = schema_registry._config
            mapping = {}
            for entry in config.get("scene_table_mapping", []):
                table = entry.get("table")
                scenes = entry.get("scenes", [])
                if table and scenes:
                    mapping[table] = scenes
            if mapping:
                logger.info(f"[SceneTableSelector] 加载场景映射: {len(mapping)} 表")
                return mapping
        except Exception as e:
            logger.warning(f"[SceneTableSelector] 加载失败，使用兜底映射: {e}")
        return self.FALLBACK_MAPPING

    def _load_relation_graph(self) -> dict:
        """[V178.10] 从 schema_registry.yaml 加载表间关联图谱"""
        try:
            config = schema_registry._config
            graph = config.get("table_relation_graph", {})
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
            if score > 0:
                scores[table] = score
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
        """生成表选择提示语，用于 Prompt 注入"""
        primary, _ = self.select_tables(user_query)
        if primary == "fqz_fymx_test":
            return """
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
        return None


# 模块级单例
scene_table_selector = SceneTableSelector()
