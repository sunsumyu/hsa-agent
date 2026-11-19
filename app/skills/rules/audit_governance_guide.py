"""
app/skills/audit_governance_guide.py
====================================
[Matt Pocock Deep Module] 医保审计安全治理准则与企业级审计红线构建器

核心职责：
1. 聚合 SchemaRegistry 注册的安全禁区约束（幻觉表黑名单、合法表前缀、敏感脱敏字段）；
2. 固化主子表分离原则与 ClickHouse 强制时间分区约束；
3. 动态协同 Neo4j 图谱能力注入指引；
4. 渲染企业级审计红线（统计基线防漏判、颗粒度聚合防膨胀、联邦侧载两阶段）。
"""

from __future__ import annotations

from typing import Any, List


class AuditGovernanceGuide:
    """医保审计治理守则生成器"""

    def build_governance_guidance(
        self,
        schema_registry_inst: Any = None,
        neo4j_manager_inst: Any = None,
    ) -> str:
        """组装完整的安全治理合规提示、图谱指引与审计红线"""
        if schema_registry_inst is None:
            from app.core.registry.schema_registry import schema_registry
            reg = schema_registry
        else:
            reg = schema_registry_inst

        forbidden_tables = reg.get_forbidden_table_names()
        valid_prefixes = reg.get_valid_prefixes()
        sensitive_fields = reg.get_sensitive_fields()

        lines: List[str] = []

        # 1. 审计治理与安全禁区
        lines.append("## 🚨 [审计治理与安全禁区 - 强制合规提示]")
        lines.append(f"- **禁止访问的幻觉表**: {', '.join([f'`{t}`' for t in forbidden_tables])} (严禁猜测，这些表物理不存在或被禁止直接访问。)")
        lines.append("- **主子表分离原则 (Header-Detail Separation)**:")
        lines.append("   - 结算主表 (`fqz_gz_jzsj_all_ql`): 仅用于核查总金额、就诊天数、时间重叠等“就诊行为”逻辑。")
        lines.append("   - 费用明细表 (`fqz_fymx_test`): 仅用于核查药品编码、耗材单价、具体项目等“收费明细”逻辑。")
        lines.append("   - 严禁在主表中搜索 `hilist_code` 等明细字段。")
        lines.append(f"- **合法表前缀**: 物理表名必须以 {', '.join([f'`{p}`' for p in valid_prefixes])} 开头。)")
        lines.append(f"- **敏感字段约束**: 涉及 {', '.join([f'`{f}`' for f in sensitive_fields])} 字段时，严禁输出明文，必须用于过滤或由系统自动脱敏。)")
        lines.append("- **性能强制分区**: 涉及明细表查询时，**必须** 显式包含 `setl_time` 时间范围过滤条件（推荐 2024 年内）。")

        # 2. 图谱能力注入指引
        if neo4j_manager_inst is None:
            from app.infra.neo4j_manager import neo4j_manager
            mgr = neo4j_manager
        else:
            mgr = neo4j_manager_inst

        try:
            graph_hints = mgr.get_audit_graph_hints()
            if graph_hints:
                lines.append(graph_hints.strip())
        except Exception:
            pass

        # 3. 企业级审计红线
        lines.append("\n## 🛑 [企业级审计红线] 严禁违反以下物理逻辑，否则召回率将严重不足：")
        lines.append("- **[红线 1: 统计学基线]**：核查'大额'或'异常频率'时，严禁使用硬编码阈值。必须先通过子查询计算 `quantile(0.95)(...)` 或 `avg(...) * 3` 作为对比基线。")
        lines.append("- **[红线 2: 颗粒度陷阱]**：核查'重复结算'、'多次就医'时，`GROUP BY` **绝对禁止** 包含 `setl_id` 或 `msg_id`。必须按 `toDate(setl_time)`、`psn_no` 和 `fixmedins_code` 聚合。")
        lines.append("- **[红线 3: 联邦两阶段]**：使用 `federated_graph_sideloader` 时，严禁在 SQL 中使用占位符。你必须分两阶段执行：(1) 先调用工具获取 `temp_table` 名；(2) 再在后续 SQL 中 JOIN 该表。")

        return "\n".join(lines)


# 单例默认实例
audit_governance_guide = AuditGovernanceGuide()
