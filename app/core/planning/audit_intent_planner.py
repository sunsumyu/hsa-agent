from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field
import re

class AuditArchetype(str, Enum):
    """医保审计四大经典业务原型"""
    EXCLUSION_MUTEX = "EXCLUSION_MUTEX"          # 互斥排他违规 (如性别/年龄/专属性冲突)
    TEMPORAL_OVERLAP = "TEMPORAL_OVERLAP"        # 时序重叠违规 (如异地同时住院)
    FREQUENCY_OUTLIER = "FREQUENCY_OUTLIER"      # 统计离群/过度违规 (如超频开药)
    MISSING_COMPANION = "MISSING_COMPANION"      # 伴随依赖缺失违规 (如无手术收麻醉费)
    GENERAL = "GENERAL"                          # 常规/聚合查询

class AuditIntent(BaseModel):
    """结构化审计意图契约 (Plan-and-Solve 输出)"""
    audit_subject: str = Field(default="合规主体", description="审计主体 (必须正向筛选的目标人群/机构)")
    violation_feature: str = Field(default="", description="客体违规特征 (涉及的项目、药品或行为)")
    archetype: AuditArchetype = Field(default=AuditArchetype.GENERAL, description="审计任务原型")
    target_gender: Optional[str] = Field(default=None, description="若涉及性别冲突，正向锁定性别: '1'=男, '2'=女")
    enforcement_guidance: Optional[str] = Field(default=None, description="给语法合成阶段的强约束提示")

class AuditIntentPlanner:
    """
    [Deep Module] 审计意图抽象规划器。
    
    职责:
    将“业务认知与主体锁定”从具体的“SQL 语法编写”中彻底解耦。
    先计划、后合成，彻底杜绝大模型在同一上下文编写 SQL 时发生主客体颠倒或注意力稀释。
    """

    FEMALE_ONLY_KEYWORDS = ["宫内节育", "节育器", "子宫", "卵巢", "输卵管", "妇科", "分娩", "流产", "刮宫", "保胎", "引产"]
    MALE_ONLY_KEYWORDS = ["前列腺", "包皮", "阴茎", "睾丸", "附睾", "精索"]

    @classmethod
    def extract_intent(cls, question: str) -> AuditIntent:
        """
        从用户原始输入或场景描述中提取结构化审计意图。
        """
        if not question or not question.strip():
            return AuditIntent()

        q = question.strip()
        q_lower = q.lower()

        # 1. 检查男性使用女性专属项目 (EXCLUSION_MUTEX)
        is_male_subject = any(kw in q for kw in ["男性", "男患者", "男参保", "男", "male"])
        has_female_item = any(kw in q for kw in cls.FEMALE_ONLY_KEYWORDS)
        
        if is_male_subject and has_female_item:
            matched_feature = next(kw for kw in cls.FEMALE_ONLY_KEYWORDS if kw in q)
            return AuditIntent(
                audit_subject="男性参保人",
                violation_feature=matched_feature,
                archetype=AuditArchetype.EXCLUSION_MUTEX,
                target_gender="1",
                enforcement_guidance=(
                    "【强约束】本场景属于性别互斥排他违规！"
                    "违规主体为男性，必须正向筛选 `gend LIKE '1%'`（或 `gend = '1'`），"
                    f"违规特征为女性专属项目（如 `hilist_name LIKE '%{matched_feature}%'`）。"
                    "严禁在 WHERE 子句中排除男性！"
                )
            )

        # 2. 检查女性使用男性专属项目 (EXCLUSION_MUTEX)
        is_female_subject = any(kw in q for kw in ["女性", "女患者", "女参保", "女", "female"])
        has_male_item = any(kw in q for kw in cls.MALE_ONLY_KEYWORDS)

        if is_female_subject and has_male_item:
            matched_feature = next(kw for kw in cls.MALE_ONLY_KEYWORDS if kw in q)
            return AuditIntent(
                audit_subject="女性参保人",
                violation_feature=matched_feature,
                archetype=AuditArchetype.EXCLUSION_MUTEX,
                target_gender="2",
                enforcement_guidance=(
                    "【强约束】本场景属于性别互斥排他违规！"
                    "违规主体为女性，必须正向筛选 `gend LIKE '2%'`（或 `gend = '2'`），"
                    f"违规特征为男性专属项目（如 `hilist_name LIKE '%{matched_feature}%'`）。"
                    "严禁在 WHERE 子句中排除女性！"
                )
            )

        # 3. 检查时序冲突原型 (TEMPORAL_OVERLAP)
        temporal_keywords = ["同日", "同时", "异地", "重叠", "并发"]
        hospital_keywords = ["住院", "就诊", "门诊", "结算", "病历"]
        if any(tk in q for tk in temporal_keywords) and any(hk in q for hk in hospital_keywords):
            return AuditIntent(
                audit_subject="参保人",
                violation_feature="异地同时/重叠结算",
                archetype=AuditArchetype.TEMPORAL_OVERLAP,
                enforcement_guidance="【时序冲突审计】必须对同一参保人在相同时间窗口内的跨机构记录进行自连接或时序区间比对。"
            )

        # 4. 检查伴随缺失原型 (MISSING_COMPANION)
        missing_keywords = ["未做", "未收取", "未发生", "无", "缺少", "缺失"]
        anesthesia_keywords = ["麻醉", "全麻", "局麻"]
        has_anesthesia = any(ak in q for ak in anesthesia_keywords)
        has_surgery = "手术" in q
        has_missing = any(mk in q for mk in missing_keywords)

        if (has_missing and has_surgery and has_anesthesia) or ("无手术" in q and has_anesthesia):
            return AuditIntent(
                audit_subject="违规就诊结算",
                violation_feature="未收取手术但计收麻醉",
                archetype=AuditArchetype.MISSING_COMPANION,
                enforcement_guidance="【伴随依赖缺失审计】必须通过 LEFT JOIN 或 NOT EXISTS 筛选计收了麻醉但无手术的记录。"
            )

        companion_pairs = [("检查", "化验"), ("配药", "处方")]
        for trigger, dep in companion_pairs:
            if any(mk in q for mk in missing_keywords) and trigger in q and dep in q:
                return AuditIntent(
                    audit_subject="违规就诊结算",
                    violation_feature=f"未收取{trigger}但计收{dep}",
                    archetype=AuditArchetype.MISSING_COMPANION,
                    enforcement_guidance=f"【伴随依赖缺失审计】必须通过 LEFT JOIN 或 NOT EXISTS 筛选计收了{dep}但无{trigger}的记录。"
                )

        # 5. 检查频次离群原型 (FREQUENCY_OUTLIER)
        outlier_keywords = ["超量", "过度", "频次", "异常偏高", "离群", "top", "排名"]
        if any(ok in q for ok in outlier_keywords):
            return AuditIntent(
                audit_subject="异常高频主体",
                violation_feature="超频/超量诊疗",
                archetype=AuditArchetype.FREQUENCY_OUTLIER,
                enforcement_guidance="【统计离群审计】必须使用 GROUP BY 进行聚合统计，严禁对明细流水进行直接 LIMIT。"
            )

        # 6. 默认常规意图
        return AuditIntent(
            audit_subject="查询目标主体",
            violation_feature="常规业务统计",
            archetype=AuditArchetype.GENERAL
        )
