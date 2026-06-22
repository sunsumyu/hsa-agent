"""
app.core — 与业务解耦的通用 Agent 框架层
"""
import sys
import importlib.util
from loguru import logger

# 1. 向上兼容导出 — 使用 __getattr__ 延迟加载，避免 app.core.__init__
#    在包导入时拉起整个 registry → tools → clickhouse/neo4j 重依赖链
__all__ = [
    "WorkflowState",
    "TaskArtifacts",
    "AuditDomainContext",
    "prompt_registry",
    "schema_registry",
    "rule_registry",
]

def __getattr__(name):
    if name == "WorkflowState":
        from app.core.state import WorkflowState
        return WorkflowState
    if name == "TaskArtifacts":
        from app.core.state import TaskArtifacts
        return TaskArtifacts
    if name == "AuditDomainContext":
        from app.core.state import AuditDomainContext
        return AuditDomainContext
    if name == "prompt_registry":
        from app.core.registry.prompt_registry import prompt_registry
        return prompt_registry
    if name == "schema_registry":
        from app.core.registry.schema_registry import schema_registry
        return schema_registry
    if name == "rule_registry":
        from app.core.registry.rule_registry import rule_registry
        return rule_registry
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# 2. 🏛️ [Core Architecture Safeguard] Core Backward Compatibility Layer
# ─────────────────────────────────────────────────────────────────────────────
# 拦截所有形如 'app.core.<module>' 的导入，并平滑将其重定向至对应的子包中：
# - app.core.context/
# - app.core.registry/

CORE_DEPRECATED_MAPPINGS = {
    # Context Engineering Submodule
    "context": "app.core.context.context",
    "context_builder": "app.core.context.context_builder",
    "context_selector": "app.core.context.context_selector",
    "funnel": "app.core.context.funnel",
    "gates": "app.core.context.gates",
    "message": "app.core.context.message",

    # Metadata Registries Submodule
    "registry": "app.core.registry.registry",
    "prompt_registry": "app.core.registry.prompt_registry",
    "rule_registry": "app.core.registry.rule_registry",
    "schema_registry": "app.core.registry.schema_registry",
    "skill_protocol": "app.core.registry.skill_protocol",
}

class CoreBackwardCompatibilityImporter:
    """
    Custom sys.meta_path hook that intercepts imports of legacy app.core flat modules
    and redirects them to the newly organized app.core.context or app.core.registry packages.
    """
    def __init__(self):
        self._resolving = set()

    def find_spec(self, fullname, path, target=None):
        if fullname in self._resolving:
            return None
        if fullname.startswith("app.core."):
            parts = fullname.split(".")
            if len(parts) == 3:
                legacy_mod_name = parts[2]
                if legacy_mod_name in CORE_DEPRECATED_MAPPINGS:
                    new_full_name = CORE_DEPRECATED_MAPPINGS[legacy_mod_name]
                    try:
                        self._resolving.add(fullname)
                        spec = importlib.util.find_spec(new_full_name)
                        if spec:
                            return spec
                    except Exception as e:
                        logger.warning(f"⚠️ [CoreCompatImporter] Failed to resolve core redirection: {legacy_mod_name} -> {new_full_name}. Error: {e}")
                    finally:
                        self._resolving.discard(fullname)
        return None

# 注册核心子包导入重映射拦截器
sys.meta_path.insert(0, CoreBackwardCompatibilityImporter())
