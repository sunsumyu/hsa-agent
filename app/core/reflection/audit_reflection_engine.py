from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from app.core.planning.audit_intent_planner import AuditIntent, AuditArchetype

class ReflectionResult(BaseModel):
    """Reflexion 诊断评估结果契约"""
    needs_retry: bool = Field(default=False, description="是否需要触发模型自愈重试")
    diagnostic_feedback: Optional[str] = Field(default=None, description="给模型的定向认知诊断反馈")
    suggested_correction: Optional[str] = Field(default=None, description="建议的修正动作或示例代码")

class AuditReflectionEngine:
    """
    [Deep Module] 审计闭环自愈反思器 (Evaluator-Optimizer).
    
    借鉴 Hello-Agents Reflexion 机制与 Anthropic Evaluator-Optimizer 规范：
    在 SQL 执行后（或静态门禁拦截时），由独立的评审员维度进行认知对账。
    当检测到“执行 0 命中且存在主体排除反向错误”或“静态恒假拦截”时，
    生成高度聚焦的结构化诊断反馈，存入上下文驱动 Coder 针对性自愈。
    """

    @classmethod
    def evaluate_execution(
        cls,
        sql: str,
        row_count: int,
        intent: Optional[AuditIntent] = None,
        error_msg: Optional[str] = None
    ) -> ReflectionResult:
        """
        评估执行结果并决定是否唤起自愈反思。
        """
        sql_clean = (sql or "").strip()
        sql_upper = sql_clean.upper()

        # 1. 优先处理错误信息 (静态门禁或 DB 异常)
        if error_msg:
            if "恒假" in error_msg or "矛盾" in error_msg:
                return ReflectionResult(
                    needs_retry=True,
                    diagnostic_feedback=(
                        f"【反思自愈诊断】检测到静态语义门禁拦截: {error_msg}。"
                        "请检查 WHERE 条件，切勿对同一枚举字段同时排除多个互斥取值！"
                        "如果目标是筛选特定主体，请务必使用正向等值/匹配条件。"
                    ),
                    suggested_correction="移除导致全排除的 NOT LIKE 条件，改用单一正向主体筛选。"
                )
            return ReflectionResult(
                needs_retry=True,
                diagnostic_feedback=f"【执行异常反思诊断】SQL 运行出错: {error_msg}，请根据报错定位语法或字段问题并修正。"
            )

        # 2. 如果已命中大于 0 条数据，且无报错，判定正常
        if row_count > 0:
            return ReflectionResult(needs_retry=False)

        # 3. 如果结果为 0 行 (Zero-Hits)，根据业务原型深入反思
        if row_count == 0 and intent:
            # 性别互斥排他原型检查 (EXCLUSION_MUTEX)
            if intent.archetype == AuditArchetype.EXCLUSION_MUTEX:
                # 检查主体是男性 (target_gender='1') 的情况
                if intent.target_gender == "1":
                    # 检查是否错误排除了男性或误判为女性
                    has_male_exclusion = any(
                        p in sql_clean for p in [
                            "gend NOT LIKE '1%'", "gend NOT LIKE '1'", "gend != '1'", 
                            "gend != 1", "gend<>'1'", "gend<>'1%'"
                        ]
                    )
                    has_female_selection = "gend LIKE '2%'" in sql_clean or "gend = '2'" in sql_clean

                    if has_male_exclusion or has_female_selection:
                        return ReflectionResult(
                            needs_retry=True,
                            diagnostic_feedback=(
                                "【反思自愈诊断】本次查询返回 0 行！"
                                "检测到当前场景属于性别互斥排他违规（男性参保人使用女性专属项目），"
                                "但你的 SQL 条件错误地排除了男性或指定了女性！"
                                "违规主体是男性，必须正向筛选男性患者，万万不可排除男性！"
                            ),
                            suggested_correction="请将 WHERE 条件修改为正向筛选男性: `gend LIKE '1%'`"
                        )

                # 检查主体是女性 (target_gender='2') 的情况
                elif intent.target_gender == "2":
                    has_female_exclusion = any(
                        p in sql_clean for p in [
                            "gend NOT LIKE '2%'", "gend NOT LIKE '2'", "gend != '2'", 
                            "gend != 2", "gend<>'2'", "gend<>'2%'"
                        ]
                    )
                    has_male_selection = "gend LIKE '1%'" in sql_clean or "gend = '1'" in sql_clean

                    if has_female_exclusion or has_male_selection:
                        return ReflectionResult(
                            needs_retry=True,
                            diagnostic_feedback=(
                                "【反思自愈诊断】本次查询返回 0 行！"
                                "检测到当前场景属于性别互斥排他违规（女性参保人使用男性专属项目），"
                                "但你的 SQL 条件错误地排除了女性或指定了男性！"
                                "违规主体是女性，必须正向筛选女性患者，万万不可排除女性！"
                            ),
                            suggested_correction="请将 WHERE 条件修改为正向筛选女性: `gend LIKE '2%'`"
                        )

        # 4. 常规查询零发现属于合规事实，放行
        return ReflectionResult(needs_retry=False)
