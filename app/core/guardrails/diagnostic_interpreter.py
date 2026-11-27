"""
Diagnostic Interpreter Deep Module.
Adheres to Matt Pocock's Deep Module design: encapsulates diagnostic reasoning,
archetype violation decoding, and remediation guidance generation behind clean static methods.
"""
from typing import Optional, List, Any


class DiagnosticInterpreter:
    """
    [Matt Pocock Deep Module] 统一门控诊断解释器。
    根据门控阶段标识、错误信息与告警列表，生成领域专家级修复建议与诊断提示。
    """

    @staticmethod
    def interpret_gate1_intent(error: Optional[str], warnings: Optional[List[str]] = None) -> Optional[str]:
        """解释 Gate 1 意图与方法论对齐结果"""
        warnings = warnings or []
        if not error and not warnings:
            return None
        if error:
            if any(kw in error for kw in ["排名", "基线", "RANKING", "分位数"]):
                return "提问为排名类查询，方法论中出现分位数阈值过滤，请精简方法论为基于指标降序排列与 LIMIT 提取。"
            return f"请重新审视提问中的审计目标与方法论对齐关系：{error}"
        return None

    @staticmethod
    def interpret_gate2_sql(
        error: Optional[str],
        warnings: Optional[List[str]] = None,
        archetypes: Optional[List[Any]] = None,
    ) -> Optional[str]:
        """解释 Gate 2 SQL 语义与领域任务原型不变式结果"""
        warnings = warnings or []
        if error:
            if any(kw in error for kw in ["GROUP BY", "LIMIT", "采样", "对账", "盘点", "明细流水"]):
                return "对于全量分析、对账或字典盘点任务，严禁使用 LIMIT 抽样明细流水，请改用 GROUP BY 聚合计算指标。"
            if any(kw in error for kw in ["恒假", "互斥", "冲突"]):
                return "检测到 SQL 在同一作用域内存在矛盾互斥谓词（如相同字段的多重不等式或排除全集），导致结果必然为空，请修正查询过滤条件。"
            return f"SQL 语义审查未通过：{error}，请根据审计业务逻辑调整 SQL 结构。"

        if warnings:
            for w in warnings:
                if any(kw in w for kw in ["RANKING", "基线", "quantile", "avg"]):
                    return "当前排名查询包含基线计算步骤，若无需相对基线偏离，请直接使用 ORDER BY 与 LIMIT。"
            return "; ".join(warnings)

        return None

    @staticmethod
    def interpret_gate3_result(error: Optional[str], warnings: Optional[List[str]] = None) -> Optional[str]:
        """解释 Gate 3 执行结果匹配情况"""
        warnings = warnings or []
        if error:
            return f"查询执行结果与预期严重不符：{error}，请检查字段投影与聚合口径。"
        if warnings:
            for w in warnings:
                if "None" in w or "执行失败" in w:
                    return "物理查询未返回有效结果（为 None），请检查底层数据库连接状态或前置 SQL 执行报错。"
            return "; ".join(warnings)
        return None
