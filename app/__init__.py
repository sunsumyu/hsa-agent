# app package
"""
🏛️ [Architecture Safeguard] Backward Compatibility Import Layer
==============================================================
Provides a completely transparent redirect for all legacy imports as files are relocated into:
- app/core/
  - app/core/context/
  - app/core/registry/
- app/agents/
- app/memory/
- app/skills/
- app/infra/
- app/reporting/
- app/api/
"""

import sys
import importlib.util
from loguru import logger

# Map legacy app.<module> name to new deeply nested app.<subpackage>.<module> path
DEPRECATED_MAPPINGS = {
    # Core Orchestration
    "agent_graph": "app.core.agent_graph",
    "booster": "app.core.booster",
    "logging_config": "app.core.logging_config",
    "observability": "app.core.observability",
    "schemas": "app.core.schemas",
    "structured_tracer": "app.core.structured_tracer",
    "prompts": "app.core.prompts",

    # Core Context Engineering (Dynamic Context Submodule)
    "context": "app.core.context.context",
    "context_builder": "app.core.context.context_builder",
    "context_selector": "app.core.context.context_selector",
    "funnel": "app.core.context.funnel",
    "gates": "app.core.context.gates",
    "message": "app.core.context.message",

    # Core Metadata Registries (Registries Submodule)
    "registry": "app.core.registry.registry",
    "prompt_registry": "app.core.registry.prompt_registry",
    "rule_registry": "app.core.registry.rule_registry",
    "schema_registry": "app.core.registry.schema_registry",
    "skill_protocol": "app.core.registry.skill_protocol",

    # Agents
    "agent": "app.agents.agent",
    "coder_agent": "app.agents.coder_agent",
    "consolidator_agent": "app.agents.consolidator_agent",
    "expert_bridge": "app.agents.expert_bridge",
    "planner_agent": "app.agents.planner_agent",
    "reflection_agent": "app.agents.reflection_agent",

    # Memory
    "experience": "app.memory.experience",
    "history": "app.memory.history",
    "compressor": "app.memory.compressor",
    "entity_extractor": "app.memory.entity_extractor",
    "message_sanitizer": "app.memory.message_sanitizer",
    "semantic_memory": "app.memory.semantic_memory",

    # Skills
    "audit_rules": "app.skills.audit_rules",
    "conflict_detector": "app.skills.conflict_detector",
    "anomaly_algorithms": "app.skills.anomaly_algorithms",
    "fast_router": "app.skills.fast_router",
    "protocol_filter": "app.skills.protocol_filter",
    "tools": "app.skills.tools",
    "security": "app.skills.security",
    "sql_validator": "app.skills.sql_validator",
    "schema_injector": "app.skills.schema_injector",
    "schema_manager": "app.skills.schema_manager",
    "semantic_layer": "app.skills.semantic_layer",

    # Infrastructure
    "db_conn": "app.infra.db_conn",
    "redis_client": "app.infra.redis_client",
    "neo4j_manager": "app.infra.neo4j_manager",
    "model_manager": "app.infra.model_manager",
    "endpoint_pool_manager": "app.infra.endpoint_pool_manager",
    "quota_fetcher": "app.infra.quota_fetcher",
    "usage_tracker": "app.infra.usage_tracker",

    # Reporting
    "report_renderer": "app.reporting.report_renderer",
    "rich_reporter": "app.reporting.rich_reporter",
    "llm_judge": "app.reporting.llm_judge",

    # Network API
    "chat_stream": "app.api.chat_stream",
    "monitor_server": "app.api.monitor_server",
    "monitor_stream": "app.api.monitor_stream",
    "perf_monitor": "app.api.perf_monitor",
}

class BackwardCompatibilityImporter:
    """
    Custom sys.meta_path hook that intercepts imports of legacy flat app modules
    and redirects them to the newly organized nested package structures.
    """
    def __init__(self):
        self._resolving = set()

    def find_spec(self, fullname, path, target=None):
        if fullname in self._resolving:
            return None
        if fullname.startswith("app."):
            parts = fullname.split(".")
            if len(parts) == 2:
                legacy_mod_name = parts[1]
                if legacy_mod_name in DEPRECATED_MAPPINGS:
                    new_full_name = DEPRECATED_MAPPINGS[legacy_mod_name]
                    try:
                        self._resolving.add(fullname)
                        spec = importlib.util.find_spec(new_full_name)
                        if spec:
                            return spec
                    except Exception as e:
                        logger.warning(f"⚠️ [CompatImporter] Failed to resolve spec redirection: {legacy_mod_name} -> {new_full_name}. Error: {e}")
                    finally:
                        self._resolving.discard(fullname)
        return None

# Register the backward compatibility importer as the first-choice routing hook
sys.meta_path.insert(0, BackwardCompatibilityImporter())
