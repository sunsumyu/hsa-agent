"""
tests/unit/test_prompt_cross_conflicts.py
==========================================
[Quality Gate] 跨提示词冲突与契约一致性自动化检测测试套件 (Cross-Prompt Conflict Detector)

遵循 Matt Pocock 设计哲学:
1. Make Illegal States Unrepresentable: 自动化拦截上下游提示词之间的规则冲突与死锁
2. Single Source of Truth (SSOT): 确保各 Prompt 对表名、字段名、法规引用的认知一致
3. Narrow Interface, Deep Verification: 遍历系统内全部 YAML 提示词，建立两两对撞约束
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Any, Set
import pytest
import yaml

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def _load_all_prompts() -> Dict[str, Dict[str, Any]]:
    """加载 prompts/ 目录下所有 yaml 提示词文件。"""
    prompts = {}
    for p in PROMPTS_DIR.glob("*.yaml"):
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            prompts[p.stem] = data
    return prompts


class TestCrossPromptConflictDetection:
    """跨提示词相互冲突自动化检测套件"""

    @pytest.fixture(autouse=True)
    def setup_prompts(self):
        self.prompts = _load_all_prompts()
        assert len(self.prompts) >= 6, f"预期加载至少 6 个核心 Prompt，实际加载 {len(self.prompts)} 个"

    # ──────────────────────────────────────────────────────────
    # 维度 1: 工具与能力集一致性 (Planner vs Coder)
    # ──────────────────────────────────────────────────────────

    def test_planner_and_coder_tool_protocol_consistency(self):
        """Planner 规划推荐的工具必须与 Coder 授权工具集严格闭环，严禁推荐下游无法闭环的规则工具。"""
        planner_content = self.prompts["planner"]["system_template"]
        coder_content = self.prompts["coder"]["system_template"]

        # Coder 声明的已授权工具白名单
        authorized_tools_in_coder = {"execute_audit_sql", "lookup_medical_schema", "federated_graph_sideloader"}
        for tool in authorized_tools_in_coder:
            assert tool in coder_content, f"Coder 提示词必须明确声明授权工具 {tool}"

        # Planner 严禁规划已经未对齐的 audit_medical_rule 工具
        assert "audit_medical_rule" not in planner_content, (
            "【工具契约死锁】Planner 提示词中包含 audit_medical_rule，而 Coder 的工具执行层仅授权 "
            "execute_audit_sql/lookup_medical_schema/federated_graph_sideloader，会导致规划漂移！"
        )

        # 联邦图谱侧载工具在 Planner 和 Coder 中必须统一命名
        assert "federated_graph_sideloader" in planner_content
        assert "federated_graph_sideloader" in coder_content

    # ──────────────────────────────────────────────────────────
    # 维度 2: 物理 Schema 字段单一事实源 (SSOT)
    # ──────────────────────────────────────────────────────────

    def test_no_fictional_hospitalization_columns_across_prompts(self):
        """全套 Prompt 中严禁出现已被证伪的伪字段 adm_date / dscg_date (真实字段为 start_date / end_date)。"""
        for prompt_id, data in self.prompts.items():
            template = data.get("system_template", "")
            assert "adm_date" not in template, (
                f"【Schema 事实源冲突】{prompt_id}.yaml 引用了假字段 'adm_date'！真实物理字段为 'start_date'。"
            )
            assert "dscg_date" not in template, (
                f"【Schema 事实源冲突】{prompt_id}.yaml 引用了假字段 'dscg_date'！真实物理字段为 'end_date'。"
            )

    def test_core_physical_tables_declaration_in_coder(self):
        """Coder 提示词中必须包含权威的 5 张物理主表声明。"""
        coder_template = self.prompts["coder"]["system_template"]
        expected_tables = [
            "fqz_fymx_test",
            "fqz_gz_jzsj_all_ql",
            "fqz_all_yy_yd",
            "fqz_admdvs",
            "fqz_drug_mcs_info_list",
        ]
        for tbl in expected_tables:
            assert tbl in coder_template, f"Coder 提示词物理清单缺少核心物理表: {tbl}"

    # ──────────────────────────────────────────────────────────
    # 维度 3: 控制流与终止状态对齐 (Coder vs Auditor)
    # ──────────────────────────────────────────────────────────

    def test_zero_findings_control_flow_consistency(self):
        """Auditor 必须对齐 Coder 的零发现终止准则，严禁盲目 REJECT 诱发死循环。"""
        coder_template = self.prompts["coder"]["system_template"]
        auditor_template = self.prompts["auditor"]["system_template"]

        # Coder 声明了零发现探针与终止准则
        assert "零发现探针与终止准则" in coder_template
        assert "微调重试" in coder_template
        assert "绝对禁止" in coder_template

        # Auditor 必须包含真阴性核准机制 (Ratification)，严禁因 0 条结果强制要求重试
        assert "零结果真阴性核准与终止" in auditor_template
        assert "判定为 PASS" in auditor_template
        assert "严禁" in auditor_template and "盲目发起 REJECT" in auditor_template

    # ──────────────────────────────────────────────────────────
    # 维度 4: 证据链上下游数据契约 (Reporter vs Coder)
    # ──────────────────────────────────────────────────────────

    def test_reporter_does_not_mandate_hallucinated_sensitivity_tiers(self):
        """Reporter 绝不能强行逼迫 LLM 捏造未经计算的 P99/P95/P90 敏感度数值。"""
        reporter_template = self.prompts["reporter"]["system_template"]

        # 绝不能出现无条件的强制输出三档对比表格指令
        assert "【强制 v2.2】三档敏感性分析" not in reporter_template
        assert "无论命中数是否为 0，都必须执行三档阈值对比" not in reporter_template

        # 必须显式声明真实循证原则：未探测时严禁虚构数值
        assert "严禁虚构未经计算的 P99/P90 数值" in reporter_template

    # ──────────────────────────────────────────────────────────
    # 维度 5: 术语唯一性与概念重载检测 (Terminology Ubiquitous Language)
    # ──────────────────────────────────────────────────────────

    def test_no_ambiguous_phase_overloading_in_coder(self):
        """Coder 提示词中不得将视图拆分命名为 Phase 1 / Phase 2，避免与基线探测的两阶段产生术语重载。"""
        coder_template = self.prompts["coder"]["system_template"]

        # 基线探测采用 Phase 1 / Phase 2
        assert "两阶段基线探测 (Two-Phase Baseline Pattern)" in coder_template

        # 视图拆分必须采用 View 1 / View 2 (双重视图取证规范)
        assert "双重视图取证规范 (Dual Evidence Views: Detail + Aggregate)" in coder_template
        assert "两阶段视图拆分规则" not in coder_template

    # ──────────────────────────────────────────────────────────
    # 维度 6: 杜绝评测集代码泄漏 (Zero Ad-hoc Whack-a-Mole Leaks)
    # ──────────────────────────────────────────────────────────

    def test_no_benchmark_case_ids_leaked_in_prompts(self):
        """所有系统 Prompt 模板中严禁泄露具体评测集 case_id (如 QA-CUST-*, QA-EDGE-*, QA-BLIND-*)。"""
        benchmark_pattern = re.compile(r"QA-(CUST|EDGE|BLIND)-\d+", re.IGNORECASE)
        for prompt_id, data in self.prompts.items():
            template = data.get("system_template", "")
            matches = benchmark_pattern.findall(template)
            assert len(matches) == 0, (
                f"【评测用例泄露】{prompt_id}.yaml 包含硬编码评测用例代号: {matches}，必须保持通用领域语义！"
            )

    # ──────────────────────────────────────────────────────────
    # 维度 7: 变量契约完整性 (Variable Contract & Slot Completeness)
    # ──────────────────────────────────────────────────────────

    def test_prompt_variables_match_template_placeholders(self):
        """验证 variables 声明列表与 system_template 中的插槽严格双向匹配，杜绝参数静默丢失。"""
        for prompt_id, data in self.prompts.items():
            declared_vars: Set[str] = set(data.get("variables", []))
            template = data.get("system_template", "")

            # 排除 messages（由 MessagesPlaceholder 处理）
            checked_vars = declared_vars - {"messages"}

            for var in checked_vars:
                placeholder = f"{{{var}}}"
                assert placeholder in template, (
                    f"【变量插槽缺失】{prompt_id}.yaml 声明了变量 '{var}'，但在 system_template 中缺少 '{placeholder}' 占位符！"
                )
