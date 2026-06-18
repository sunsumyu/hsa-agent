"""
app/core/scene_table_selector.py
=================================
[V1.0] 场景感知表选择器 — 自动根据用户查询选择正确的物理表

核心职责：
- 分析用户查询中的关键词
- 根据 scene_table_mapping 规则选择正确的表
- 返回目标表列表供 ContextBuilder 注入 Schema
- 生成强制性表选择提示语用于 Prompt 注入
"""

import re
from typing import List, Tuple, Optional
from loguru import logger
from app.core.registry.schema_registry import schema_registry


class SceneTableSelector:
    """场景感知的物理表选择器"""

    # 硬编码场景关键词映射（配置文件加载失败时兜底）
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
                logger.info(f"[SceneTableSelector] 加载场景映射: {len(mapping)} 表, {config.get('scene_table_mapping', [])}")
                return mapping
        except Exception as e:
            logger.warning(f"[SceneTableSelector] 加载失败，使用兜底映射: {e}")
        return self.FALLBACK_MAPPING

    def select_tables(self, user_query: str) -> Tuple[str, List[str]]:
        """
        根据用户查询选择目标表

        Args:
            user_query: 用户原始查询

        Returns:
            (primary_table, all_tables): 主表名 + 所有相关表列表
        """
        query_lower = user_query.lower()

        # 计算各表的匹得分
        scores = {}
        for table, keywords in self._mapping.items():
            score = sum(1 for kw in keywords if kw.lower() in query_lower)
            if score > 0:
                scores[table] = score

        if not scores:
            # 无场景匹配，使用默认主表
            primary = schema_registry.get_main_table()
            logger.info(f"[SceneTableSelector] 无场景匹配，使用默认主表: {primary}")
            return primary, [primary]

        # 选择得分最高的表作为主表
        primary = max(scores, key=scores.get)
        all_tables = list(scores.keys())

        logger.info(f"[SceneTableSelector] 场景匹配结果: 主表={primary}, 相关表={all_tables}, 得分={scores}")
        return primary, all_tables

    def get_enforcement_hint(self, user_query: str) -> Optional[str]:
        """
        生成强制性表选择提示语，用于 Prompt 注入

        当检测到 fqz_fymx_test 场景时，返回强制性的 SQL 编写指引

        Args:
            user_query: 用户原始查询

        Returns:
            强制性提示语，如果不需要强制则返回 None
        """
        primary, _ = self.select_tables(user_query)

        if primary == "fqz_fymx_test":
            return """
【⚠️ 物理表强制选择红线 (ENFORCEMENT LAYER)】
根据场景关键词检测，你**必须直接查 `fqz_fymx_test`**，严禁使用其他表！

理由：
1. 乡镇卫生院/村卫生室/门诊统筹场景的费用数据存储在 `fqz_fymx_test`
2. `fqz_fymx_test.fixmedins_name` 是真实中文机构名，可 LIKE 匹配
3. `fqz_gz_jzsj_all_ql.fixmedins_name` 是加密混淆字段，无法中文匹配
4. 两表 setl_id 完全不重叠，JOIN 会导致数据丢失

强制 SQL 模板：
```sql
SELECT
    toDate(toDateTime(substring(trim(setl_time),1,19))) AS setl_date,
    trim(fixmedins_name) AS inst,
    trim(hilist_name) AS item,
    count(DISTINCT trim(psn_no)) AS patient_count,
    dateDiff('second',
             min(toDateTime(substring(trim(setl_time),1,19))),
             max(toDateTime(substring(trim(setl_time),1,19)))) AS span_sec
FROM default.fqz_fymx_test
WHERE trim(fixmedins_name) LIKE '%卫生%'
GROUP BY setl_date, inst, item
HAVING patient_count >= 5 AND span_sec <= 300
ORDER BY patient_count DESC LIMIT 50
```

注意事项：
- 必须用 `toDateTime(substring(trim(setl_time),1,19))` 转换时间戳
- 必须用 `trim(...)` 清理字符串字段
- med_type 编码：11=门诊统筹，21=住院，53_04=特病门诊
- 严禁使用 `fqz_gz_jzsj_all_ql`
"""

        return None


# 模块级单例
scene_table_selector = SceneTableSelector()
