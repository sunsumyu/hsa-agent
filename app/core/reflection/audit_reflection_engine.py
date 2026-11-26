from typing import Optional
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

    在 SQL 执行后（或静态门禁拦截时），由独立的评审员维度进行认知对账。
    当检测到“执行 0 命中且存在主体排除反向错误”或“静态恒假拦截”时，
    生成高度聚焦的结构化诊断反馈，存入上下文驱动 Coder 针对性自愈。
    """

    @classmethod
    def _diagnose_error_message(cls, error_msg: str) -> ReflectionResult:
        if "伴随依赖缺失" in error_msg or "单行伪排除" in error_msg:
            return ReflectionResult(
                needs_retry=True,
                diagnostic_feedback=(
                    f"【反思自愈诊断】检测到伴随依赖缺失单行伪排除反模式拦截: {error_msg}。"
                    "切勿在单行明细的 WHERE 中同时排除伴随字段！"
                    "必须在就诊/结算粒度（如 `setl_id`）使用跨行子查询进行排查。"
                ),
                suggested_correction="改用跨行子查询: `WHERE hilist_name LIKE '%伴随项目%' AND setl_id NOT IN (SELECT setl_id FROM fqz_fymx_test WHERE hilist_name LIKE '%前置项目%')`",
            )
        if "恒假" in error_msg or "矛盾" in error_msg:
            return ReflectionResult(
                needs_retry=True,
                diagnostic_feedback=(
                    f"【反思自愈诊断】检测到静态语义门禁拦截: {error_msg}。"
                    "请检查 WHERE 条件，切勿对同一枚举字段同时排除多个互斥取值！"
                    "如果目标是筛选特定主体，请务必使用正向等值/匹配条件。"
                ),
                suggested_correction="移除导致全排除的 NOT LIKE 条件，改用单一正向主体筛选。",
            )
        return ReflectionResult(
            needs_retry=True,
            diagnostic_feedback=f"【执行异常反思诊断】SQL 运行出错: {error_msg}，请根据报错定位语法或字段问题并修正。",
        )

    @classmethod
    def _diagnose_gender_mutex_zero_hits(
        cls,
        sql_clean: str,
        target_gender: Optional[str],
    ) -> Optional[ReflectionResult]:
        specs = {
            "1": (
                "男性", "女性专属项目", "男性患者",
                ["gend NOT LIKE '1%'", "gend NOT LIKE '1'", "gend != '1'", "gend != 1", "gend<>'1'", "gend<>'1%'"],
                ("gend LIKE '2%'", "gend = '2'"),
                "gend LIKE '1%'",
            ),
            "2": (
                "女性", "男性专属项目", "女性患者",
                ["gend NOT LIKE '2%'", "gend NOT LIKE '2'", "gend != '2'", "gend != 2", "gend<>'2'", "gend<>'2%'"],
                ("gend LIKE '1%'", "gend = '1'"),
                "gend LIKE '2%'",
            ),
        }
        spec = specs.get(target_gender or "")
        if not spec:
            return None
        subj_label, item_label, pos_label, excl_patterns, opp_patterns, fix_hint = spec
        has_excl = any(p in sql_clean for p in excl_patterns)
        has_opp = any(p in sql_clean for p in opp_patterns)
        if has_excl or has_opp:
            opp_label = "女性" if target_gender == "1" else "男性"
            return ReflectionResult(
                needs_retry=True,
                diagnostic_feedback=(
                    "【反思自愈诊断】本次查询返回 0 行！"
                    f"检测到当前场景属于性别互斥排他违规（{subj_label}参保人使用{item_label}），"
                    f"但你的 SQL 条件错误地排除了{subj_label}或指定了{opp_label}！"
                    f"违规主体是{subj_label}，必须正向筛选{pos_label}，万万不可排除{subj_label}！"
                ),
                suggested_correction=f"请将 WHERE 条件修改为正向筛选{subj_label}: `{fix_hint}`",
            )
        return None

    @classmethod
    def _diagnose_zero_hit_archetype(
        cls,
        sql_clean: str,
        sql_upper: str,
        intent: AuditIntent,
    ) -> ReflectionResult:
        if intent.archetype == AuditArchetype.EXCLUSION_MUTEX:
            gender_res = cls._diagnose_gender_mutex_zero_hits(sql_clean, intent.target_gender)
            if gender_res is not None:
                return gender_res
        elif intent.archetype == AuditArchetype.REVERSAL_REFUND:
            has_neg = "< 0" in sql_clean or "<0" in sql_clean
            if not has_neg or "> 0" in sql_clean or ">0" in sql_clean or "ABS(" in sql_upper:
                return ReflectionResult(
                    needs_retry=True,
                    diagnostic_feedback=(
                        "【反思自愈诊断】本次查询返回 0 行！"
                        "检测到当前场景属于负数冲正与退费记录核查，"
                        "但你的 SQL 条件缺少了对负数金额的筛选（如 `det_item_fee_sumamt < 0`），"
                        "或者错误地写成了正数过滤/ABS绝对值！请确保精确筛选金额小于 0 的退费明细。"
                    ),
                    suggested_correction="请在 WHERE 条件中增加正向负数筛选: `det_item_fee_sumamt < 0`",
                )
        elif intent.archetype == AuditArchetype.ZERO_FINDINGS_BASELINE:
            return ReflectionResult(
                needs_retry=False,
                diagnostic_feedback="【合规零发现】排查规则完成扫描，未发现违规记录，属于正常合规事实。",
            )
        elif intent.archetype == AuditArchetype.SPLIT_BILLING:
            return ReflectionResult(
                needs_retry=True,
                diagnostic_feedback=(
                    "【反思自愈诊断】本次查询返回 0 行！"
                    "检测到当前场景属于分解收费与套收违规排查（如主干手术与子步骤拆开计费），"
                    "如果你的 SQL 在单条明细的 WHERE 中对同一字段施加了多个互斥条件，或者缺少就诊粒度的联合统计，"
                    "请改用同一就诊（setl_id）的自连接 JOIN 或按 setl_id 分组统计项目种类（HAVING count(DISTINCT hilist_name) > 1）！"
                ),
                suggested_correction="请使用同一结算自连接或 GROUP BY setl_id 进行跨行多项目联合筛查。",
            )
        elif intent.archetype == AuditArchetype.DRUG_RESALE:
            return ReflectionResult(
                needs_retry=True,
                diagnostic_feedback=(
                    "【反思自愈诊断】本次查询返回 0 行！"
                    "检测到当前场景属于药贩子套现与高频异常购药网络排查，"
                    "违规特征体现在参保人高频次购药或定点闭环，单次明细剂量常属正常。"
                    "请务必按参保人维度聚合（GROUP BY psn_no 或 psn_no, toDate(setl_time)），并比对频次与定点机构数门限！"
                ),
                suggested_correction="请改用按参保人聚合统计: `GROUP BY psn_no HAVING count() > 门限`",
            )
        return ReflectionResult(needs_retry=False)

    @classmethod
    def evaluate_execution(
        cls,
        sql: str,
        row_count: int,
        intent: Optional[AuditIntent] = None,
        error_msg: Optional[str] = None,
    ) -> ReflectionResult:
        """评估执行结果并决定是否唤起自愈反思。"""
        if error_msg:
            return cls._diagnose_error_message(error_msg)
        if row_count > 0:
            return ReflectionResult(needs_retry=False)
        if row_count == 0 and intent:
            sql_clean = (sql or "").strip()
            return cls._diagnose_zero_hit_archetype(sql_clean, sql_clean.upper(), intent)
        return ReflectionResult(needs_retry=False)
