"""
app/skills
==========
Argus Agent Skills Package.

Organized into 5 cohesive subpackages:
- sql: ClickHouse SQL execution, pipeline, linter, validation, and sanitization.
- schema: Metadata discovery, schema injection, domain routing, and semantic layer.
- security: Neuro-symbolic security guards, probe protection, conflict and safe math evaluators.
- rules: Audit rules catalog, anomaly detection, operator runner, and execution pipeline.
- federated: Federated graph queries, entity sideloader, expert KB, and routing.

Maintains 100% backward compatibility with legacy flat imports (`app.skills.<module>`)
via a transparent meta-path redirect finder.
"""

import sys
import importlib
import importlib.abc
import importlib.machinery

SUBPACKAGES = ("sql", "schema", "security", "rules", "federated")

# Subpackage mapping for fast O(1) resolution
_MODULE_MAP = {
    # SQL
    "sql_tools": "sql",
    "sql_execution": "sql",
    "sql_execution_pipeline": "sql",
    "sql_validator": "sql",
    "sql_linter_rules": "sql",
    "sql_injection_guard": "sql",
    "sql_result_sanitizer": "sql",
    "sql_complexity_auditor": "sql",
    "sql_equivalence_checker": "sql",
    "sql_ast_security_auditor": "sql",

    # Schema
    "schema_tools": "schema",
    "schema_manager": "schema",
    "schema_injector": "schema",
    "schema_domain_router": "schema",
    "schema_field_pruner": "schema",
    "schema_truth_validator": "schema",
    "medical_schema": "schema",
    "semantic_layer": "schema",
    "semantic_encyclopedia_parser": "schema",
    "semantic_hyde_generator": "schema",
    "semantic_prompt_formatter": "schema",

    # Security (note: `security` itself is a subpackage re-exporting security.py)
    "probe_guard": "security",
    "protocol_filter": "security",
    "conflict_detector": "security",
    "safe_math_evaluator": "security",

    # Rules
    "audit_rules": "rules",
    "rule_catalog": "rules",
    "rule_execution": "rules",
    "rule_pattern_resolver": "rules",
    "rule_tolerance_policy": "rules",
    "analysis_tools": "rules",
    "analysis_operator_runner": "rules",
    "analysis_operator_resolver": "rules",
    "anomaly_algorithms": "rules",
    "audit_execution_pipeline": "rules",
    "audit_governance_guide": "rules",

    # Federated
    "federated_query": "federated",
    "federated_graph_executor": "federated",
    "federated_sideload_buffer": "federated",
    "expert_knowledge_retriever": "federated",
    "fast_router": "federated",
    "fast_route_matcher": "federated",
    "law_rag_tools": "federated",
    "memory_tools": "federated",
    "audit_note_store": "federated",
    "tools": "federated",
}


class _SkillRedirectLoader(importlib.abc.Loader):
    def __init__(self, target_fullname: str):
        self.target_fullname = target_fullname

    def create_module(self, spec):
        return importlib.import_module(self.target_fullname)

    def exec_module(self, module):
        pass


class _SkillMetaPathFinder(importlib.abc.MetaPathFinder):
    """Intercepts legacy `app.skills.<module>` imports and delegates to the appropriate subpackage."""

    def find_spec(self, fullname: str, path, target=None):
        if not fullname.startswith("app.skills."):
            return None
        parts = fullname.split(".")
        if len(parts) != 3:
            return None
        mod_name = parts[-1]
        if mod_name in SUBPACKAGES:
            return None

        subpkg = _MODULE_MAP.get(mod_name)
        if subpkg:
            target_fullname = f"app.skills.{subpkg}.{mod_name}"
            return importlib.machinery.ModuleSpec(
                fullname,
                _SkillRedirectLoader(target_fullname),
            )
        return None


# Register finder idempotently
if not any(isinstance(finder, _SkillMetaPathFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _SkillMetaPathFinder())
