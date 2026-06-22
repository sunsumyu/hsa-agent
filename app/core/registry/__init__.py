"""
Registry package — lazy exports to avoid heavy import chain at package init.

skill_registry in particular triggers app.skills.tools (714 lines with
ClickHouse/Neo4j/langchain imports) on instantiation, so it must not be
eagerly loaded when app.core.registry is imported.
"""

__all__ = ["skill_registry", "prompt_registry", "rule_registry", "schema_registry"]

def __getattr__(name):
    if name == "skill_registry":
        from app.core.registry.registry import skill_registry
        return skill_registry
    if name == "prompt_registry":
        from app.core.registry.prompt_registry import prompt_registry
        return prompt_registry
    if name == "rule_registry":
        from app.core.registry.rule_registry import rule_registry
        return rule_registry
    if name == "schema_registry":
        from app.core.registry.schema_registry import schema_registry
        return schema_registry
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
