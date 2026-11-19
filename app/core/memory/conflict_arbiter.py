"""
app/core/memory/conflict_arbiter.py
===================================
[Matt Pocock Deep Module] 记忆与便签时序冲突仲裁器 (Memory Conflict Arbiter)
实现时序信念修正 (Temporal Belief Revision) 与语义极性互斥覆写 (Last-Write-Wins)。

涵盖 5 大工程级边界冲突：
1. 数值/口径突变冲突 (Threshold Mutation)
2. 多跳链式时序反转 (Multi-Hop Flip-Flop Chain A -> B -> A)
3. 集合包含与范围移出 (Set Inclusion vs Exclusion)
4. 特例下级覆盖通则上级 (Specificity Hierarchy: Exception Overrides General)
5. 时效区间自然逾期失效 (Time-Bounded Scope & Expiration Invalidation)
"""

import re
import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from loguru import logger
from app.core.memory.base import MemoryItem


@dataclass
class MemoryAssertion:
    """单个记忆或便签命题的结构化表征"""
    raw_text: str
    entity: str
    attribute: str
    polarity: str  # "POSITIVE", "NEGATIVE", "NEUTRAL", "EXPIRED"
    timestamp: datetime.datetime
    original_index: int
    is_superseded: bool = False
    superseded_by: Optional[str] = None


@dataclass
class ConflictResolutionResult:
    """冲突仲裁结果"""
    active_assertions: List[MemoryAssertion]
    superseded_assertions: List[MemoryAssertion]
    conflicts_detected: int


class MemoryConflictArbiter:
    """
    记忆冲突仲裁器：
    解决偏好突变、时序横跳、数值口径调整、特例覆盖通则、过期时效失效等语义层面的认知矛盾。
    """

    # 否定/排除/免除极性词库
    NEGATIVE_KEYWORDS = [
        "不", "没", "忌", "非", "未", "撤销", "解除", "排除", "移出",
        "无需", "免除", "免检", "合规", "正常", "无违规", "不吃", "不喜欢", "取消"
    ]

    # 肯定/风险/喜好极性词库
    POSITIVE_KEYWORDS = [
        "喜欢", "偏好", "爱吃", "必须", "纳入", "列为", "判定为",
        "违规", "嫌疑", "异常", "高危", "重点监控", "集中", "超标", "启用", "恢复", "全量穿透"
    ]

    def resolve_note_conflicts(self, raw_notes: str, strip_superseded: bool = True) -> str:
        """
        对外部便签簿的多条记录进行语义冲突检测与时序覆写
        :param raw_notes: 由 '---' 分隔的原始便签内容
        :param strip_superseded: True 则物理剔除作废记录；False 则显式标注 [已作废 / SUPERSEDED]
        :return: 仲裁重构后的便签内容
        """
        if not raw_notes or not raw_notes.strip():
            return ""

        parts = [p.strip() for p in raw_notes.split("---") if p.strip()]
        if len(parts) <= 1:
            return raw_notes

        assertions = []
        now = datetime.datetime.now()

        for idx, part in enumerate(parts):
            ts = self._extract_timestamp(part, fallback_time=now + datetime.timedelta(seconds=idx))
            entity, attribute, polarity = self._extract_semantic_slot(part, now=now)
            
            assertions.append(MemoryAssertion(
                raw_text=part,
                entity=entity,
                attribute=attribute,
                polarity=polarity,
                timestamp=ts,
                original_index=idx
            ))

        # 执行时序与层级覆写仲裁
        resolved = self._arbitrate_assertions(assertions)

        if strip_superseded:
            active_parts = [a.raw_text for a in resolved.active_assertions if not a.is_superseded]
            return "\n\n---\n\n".join(active_parts)
        else:
            output_parts = []
            for a in assertions:
                if a.is_superseded:
                    revised = f"## ⚠️ [已作废 / SUPERSEDED - {a.superseded_by or '结论已被后续更正'}]\n{a.raw_text}"
                    output_parts.append(revised)
                else:
                    if a.superseded_by:
                        revised = f"## 📌 [最新事实生效于 {a.timestamp.strftime('%Y-%m-%d')}，已覆写历史记录]\n{a.raw_text}"
                        output_parts.append(revised)
                    else:
                        output_parts.append(a.raw_text)
            return "\n\n---\n\n".join(output_parts)

    def resolve_memory_items(self, items: List[MemoryItem]) -> List[MemoryItem]:
        """
        对结构化 MemoryItem 列表进行冲突仲裁并返回消歧后的最新项列表
        """
        if not items or len(items) <= 1:
            return items

        assertions = []
        now = datetime.datetime.now()

        for idx, item in enumerate(items):
            content_str = str(item.content)
            ts = item.timestamp if isinstance(item.timestamp, datetime.datetime) else now + datetime.timedelta(seconds=idx)
            
            entity = item.metadata.get("entity")
            attribute = item.metadata.get("attribute")
            polarity = item.metadata.get("polarity")

            if not (entity and attribute and polarity):
                inferred_entity, inferred_attr, inferred_pol = self._extract_semantic_slot(content_str, now=now)
                entity = entity or inferred_entity
                attribute = attribute or inferred_attr
                polarity = polarity or inferred_pol

            assertions.append(MemoryAssertion(
                raw_text=content_str,
                entity=entity,
                attribute=attribute,
                polarity=polarity,
                timestamp=ts,
                original_index=idx
            ))

        resolved = self._arbitrate_assertions(assertions)
        survived_indices = {a.original_index for a in resolved.active_assertions if not a.is_superseded}
        return [item for idx, item in enumerate(items) if idx in survived_indices]

    def _arbitrate_assertions(self, assertions: List[MemoryAssertion]) -> ConflictResolutionResult:
        """核心仲裁算法：按 (Entity, Attribute) 聚合，时序冲突与层级覆盖裁决"""
        groups: Dict[Tuple[str, str], List[MemoryAssertion]] = {}
        for a in assertions:
            key = (a.entity.strip().lower(), a.attribute.strip().lower())
            groups.setdefault(key, []).append(a)

        active = []
        superseded = []
        conflict_count = 0

        for key, group in groups.items():
            # 1. 优先处理自然过期命题 (Case 5: Time-Bounded Scope Expiration)
            unexpired_group = []
            for item in group:
                if item.polarity == "EXPIRED":
                    item.is_superseded = True
                    item.superseded_by = "历史适用时效已届满自然失效"
                    superseded.append(item)
                    conflict_count += 1
                else:
                    unexpired_group.append(item)

            if not unexpired_group:
                continue

            if len(unexpired_group) == 1:
                active.append(unexpired_group[0])
                continue

            # 按时间戳从早到晚排序
            unexpired_group.sort(key=lambda x: x.timestamp)
            polarities = {item.polarity for item in unexpired_group}

            # 判定冲突标准：
            # A. 存在互斥极性 (POSITIVE vs NEGATIVE)
            # B. 数值/口径阈值突变 (THRESHOLD_AMOUNT)
            # C. 报告排版偏好突变 (REPORT_FORMAT_TABLE)
            has_conflict = (
                (len(polarities) > 1 and ("POSITIVE" in polarities and "NEGATIVE" in polarities))
                or key[1].upper() in ("THRESHOLD_AMOUNT", "REPORT_FORMAT_TABLE")
            )

            if has_conflict:
                conflict_count += 1
                latest = unexpired_group[-1]
                logger.info(
                    f"⚔️ [MemoryConflictArbiter] 发现语义事实冲突: 实体『{key[0]}』维度『{key[1]}』 "
                    f"最新事实 ({latest.timestamp.strftime('%Y-%m-%d %H:%M:%S')}) 自动覆写 {len(unexpired_group)-1} 条旧记录！"
                )
                
                # 最新的获胜 (Last-Write-Wins, 支持链式反转 A -> B -> A)
                latest.is_superseded = False
                latest.superseded_by = f"覆盖了历史 {len(unexpired_group)-1} 条矛盾声明"
                active.append(latest)

                for older in unexpired_group[:-1]:
                    older.is_superseded = True
                    older.superseded_by = f"已被最新事实 ({latest.timestamp.strftime('%Y-%m-%d')}) 覆盖作废"
                    superseded.append(older)
            else:
                active.extend(unexpired_group)

        # 2. Case 4: 特例下级覆盖通则上级冲突 (Specificity Hierarchy)
        # 若存在具体重点实体的 AUDIT_EXEMPTION (如某卫生室取消免检/强制穿透)，且存在通用通则 (如基层医疗机构小额免检)
        specific_exceptions = [
            a for a in active 
            if a.attribute == "AUDIT_EXEMPTION" and a.entity not in ("基层医疗机构", "通则", "GLOBAL") and not a.is_superseded
        ]
        if specific_exceptions:
            general_exemptions = [
                a for a in active 
                if a.attribute == "AUDIT_EXEMPTION" and a.entity in ("基层医疗机构", "通则", "GLOBAL")
            ]
            for gen in general_exemptions:
                gen.is_superseded = True
                gen.superseded_by = "已被涉案重点机构特例穿透规则覆盖"
                if gen in active:
                    active.remove(gen)
                superseded.append(gen)
                conflict_count += 1

        # 恢复原始相对顺序
        active.sort(key=lambda x: x.original_index)
        superseded.sort(key=lambda x: x.original_index)

        return ConflictResolutionResult(
            active_assertions=active,
            superseded_assertions=superseded,
            conflicts_detected=conflict_count
        )

    def _extract_semantic_slot(self, text: str, now: Optional[datetime.datetime] = None) -> Tuple[str, str, str]:
        """从自然语言文本中提取 (实体, 属性维度, 极性)"""
        text_clean = text.strip()
        now = now or datetime.datetime.now()

        # 0. 时效区间逾期检测 (Case 5: Time-Bounded Scope Expiration)
        validity_match = re.search(r'(\d{4}-\d{2}-\d{2})\s*(?:至|到|-)\s*(\d{4}-\d{2}-\d{2})', text_clean)
        if validity_match:
            try:
                end_date = datetime.datetime.strptime(validity_match.group(2), "%Y-%m-%d")
                if end_date < now:
                    # 历史时段已自然届满失效
                    return "TEMPORAL_VALIDITY", "TIME_BOUNDED_EXEMPTION", "EXPIRED"
            except Exception:
                pass

        # 1. 实体识别 (Entity)
        entity = "GLOBAL"
        drug_match = re.search(r'(黄体酮(?:注射液)?|地屈孕酮(?:片)?|益母草(?:颗粒)?|乌鸡白凤(?:丸)?)', text_clean)
        inst_match = re.search(
            r'([^\s，,。；;：:\(\)\"\'\[\]]{2,30}?(?:卫生室|医院|卫生院|诊所|药店|大药房|门诊部))',
            text_clean
        )

        if any(w in text_clean for w in ["基层医疗机构", "所有一级", "所有定点"]):
            entity = "基层医疗机构"
        elif any(w in text_clean for w in ["定点药店", "零售药店", "医药机构"]):
            entity = "定点药店"
        elif inst_match:
            raw_ent = inst_match.group(1).strip()
            entity = re.sub(r'^(?:针对|关于|对)\s*', '', raw_ent)
        elif drug_match and any(w in text_clean for w in ["药品", "清单", "黑名单", "移出", "核查范围", "专项"]):
            entity = drug_match.group(1).strip()
        elif any(k in text_clean for k in ["用户", "本人", "我", "客户"]):
            entity = "USER_PREFERENCE"

        # 2. 属性维度识别 (Attribute)
        attribute = "GENERAL"
        if any(w in text_clean for w in ["表格", "排版", "无序列表", "bullet", "纯文字", "列表"]):
            attribute = "REPORT_FORMAT_TABLE"
        elif any(w in text_clean for w in ["阈值", "大额购药", "大额排查", "单笔结算金额", "金额标准"]):
            attribute = "THRESHOLD_AMOUNT"
        elif any(w in text_clean for w in ["移出", "纳入", "清单", "黑名单", "核查范围"]):
            attribute = "SPECIAL_DRUG_SCOPE"
        elif any(w in text_clean for w in ["免检", "豁免", "取消免检", "全量穿透", "取消所有小额免检"]):
            attribute = "AUDIT_EXEMPTION"
        elif any(w in text_clean for w in ["合规", "违规", "嫌疑", "监控", "正常", "异常", "刷单", "重点对象"]):
            attribute = "AUDIT_RISK_STATUS"

        # 3. 极性识别 (Polarity)
        has_negative = False
        for kw in self.NEGATIVE_KEYWORDS:
            if kw in text_clean:
                has_negative = True
                break

        has_positive = False
        for kw in self.POSITIVE_KEYWORDS:
            if kw in text_clean:
                has_positive = True
                break

        if has_negative and has_positive:
            # 组合语境消歧
            if any(w in text_clean for w in ["不喜欢", "不吃", "忌", "无违规", "免检", "取消表格", "移出", "取消所有小额免检"]):
                polarity = "NEGATIVE"
            elif any(w in text_clean for w in ["重新启用", "恢复", "存在违规", "列为嫌疑", "下调为"]):
                polarity = "POSITIVE"
            else:
                polarity = "NEGATIVE"
        elif has_negative:
            polarity = "NEGATIVE"
        elif has_positive:
            polarity = "POSITIVE"
        else:
            polarity = "NEUTRAL"

        return entity, attribute, polarity

    def _extract_timestamp(self, text: str, fallback_time: datetime.datetime) -> datetime.datetime:
        """从便签文本中提取标准时间戳，失败则返回 fallback_time"""
        date_match = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', text)
        if date_match:
            try:
                return datetime.datetime.strptime(date_match.group(1), "%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
        
        date_short_match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
        if date_short_match:
            try:
                return datetime.datetime.strptime(date_short_match.group(1), "%Y-%m-%d")
            except Exception:
                pass

        return fallback_time


# 单例导出
memory_conflict_arbiter = MemoryConflictArbiter()
