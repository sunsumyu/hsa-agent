import re
import datetime
from typing import List, Dict, Any, Optional
from loguru import logger
from app.core.query_classifier import QueryType

class HistoryContextFilter:
    """历史上下文智能过滤器，对历史便签和经验库文档进行语义和时效性校验与降权"""

    def filter_relevant_notes(
        self,
        notes_raw: str,
        current_query: str,
        query_type: QueryType
    ) -> str:
        """
        过滤并重构外部审计便签内容：
        1. 问题类型不匹配：如果当前查询为 RANKING，则过滤掉带有聚合/分组（GROUP BY）特征的便签，防止误导。
        2. 时间衰减：便签日期若超过 30 天，则降低其可信度描述；若超过 90 天，则直接抛弃该便签。
        3. 纠错次数衰减：若便签中记录有多次修复/纠偏标识，直接视作低可信度便签进行丢弃或打上警告标签。
        """
        if not notes_raw:
            return ""

        # 按 '---' 分割便签
        parts = [p.strip() for p in notes_raw.split("---") if p.strip()]
        filtered_parts = []
        now = datetime.datetime.now()

        for part in parts:
            # 忽略配置信息块
            if "[TIME_DECAY_CONFIG]" in part:
                filtered_parts.append(part)
                continue

            # 1. 提取时间戳并进行时效衰减
            # 匹配形如: 2026-06-20 03:00:00
            date_match = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', part)
            if date_match:
                try:
                    note_time = datetime.datetime.strptime(date_match.group(1), "%Y-%m-%d %H:%M:%S")
                    days_passed = (now - note_time).days
                    if days_passed > 90:
                        logger.info(f"⏳ [HistoryFilter] 外部便签已过期 (>90d, 实际 {days_passed}d)，已被物理过滤。")
                        continue
                    elif days_passed > 30:
                        logger.info(f"⏳ [HistoryFilter] 外部便签已超过 30天 (实际 {days_passed}d)，对其可信度降权标示。")
                        part = part.replace("📌", "⚠️ [已衰减便签 - 超过30天仅供参考]")
                except Exception as e:
                    logger.warning(f"⚠️ [HistoryFilter] 解析外部便签日期格式错误: {e}")

            # 2. 意图/问题类型对齐校验（防御性过滤）
            part_lower = part.lower()
            if query_type in (QueryType.RANKING, QueryType.TOP_N):
                # 如果当前为排序类问题，过滤掉包含 "GROUP BY" 且包含聚合特征的便签，以防止错误的 SQL 结构污染
                if "group by" in part_lower and ("sum(" in part_lower or "count(" in part_lower):
                    logger.warning("❌ [HistoryFilter] 发现可能导致语义偏离的 GROUP BY 聚合历史便签，已将其过滤。")
                    continue
            
            # 3. 校验纠错标记（包含多次重试或错误记录的便签降低信任）
            if "error" in part_lower or "failed" in part_lower or "重试" in part_lower:
                part = part.replace("📌", "⚠️ [低信度便签 - 历史运行中曾发生过纠错]")

            filtered_parts.append(part)

        return "\n\n---\n\n".join(filtered_parts)

# 单例导出
history_context_filter = HistoryContextFilter()
