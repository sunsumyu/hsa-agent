"""
app/core/bootstrap.py
=====================
Service registration entry point. Called during application startup (lifespan)
to register all singletons into the ServiceProvider DI container.

Each service is registered as a lazy factory — the instance is not created
until the first resolve() call. This breaks import-time side effects (DB
connections, API client init) from module import.
"""

from loguru import logger
from app.core.container import ServiceProvider


def register_services():
    """Register all infrastructure and domain singletons into the DI container."""
    logger.info("[Bootstrap] Registering services into ServiceProvider...")

    # ── Infrastructure layer ──────────────────────────────────
    ServiceProvider.register("settings", lambda: __import__(
        "app.core.config", fromlist=["settings"]).settings)
    ServiceProvider.register("usage_tracker", lambda: __import__(
        "app.infra.usage_tracker", fromlist=["UsageTracker"]).UsageTracker())
    ServiceProvider.register("model_manager", lambda: __import__(
        "app.infra.model_manager", fromlist=["ModelManager"]).ModelManager())
    ServiceProvider.register("endpoint_pool_manager", lambda: __import__(
        "app.infra.endpoint_pool_manager", fromlist=["EndpointPoolManager"]).EndpointPoolManager())
    ServiceProvider.register("redis_manager", lambda: __import__(
        "app.infra.redis_client", fromlist=["RedisClient"]).RedisClient())
    ServiceProvider.register("neo4j_manager", lambda: __import__(
        "app.infra.neo4j_manager", fromlist=["Neo4jManager"]).Neo4jManager())
    ServiceProvider.register("field_kg", lambda: __import__(
        "app.infra.field_knowledge_graph", fromlist=["FieldKnowledgeGraph"]).FieldKnowledgeGraph())
    ServiceProvider.register("perf_monitor", lambda: __import__(
        "app.api.perf_monitor", fromlist=["PerfMonitor"]).PerfMonitor())
    ServiceProvider.register("observability", lambda: __import__(
        "app.core.observability_service", fromlist=["ObservabilityService"]).ObservabilityService())

    # ── Core services ─────────────────────────────────────────
    ServiceProvider.register("llm_provider", lambda: __import__(
        "app.core.llm_provider", fromlist=["LLMProvider"]).LLMProvider())
    ServiceProvider.register("booster", lambda: __import__(
        "app.core.booster", fromlist=["PrecisionBooster"]).PrecisionBooster())
    ServiceProvider.register("permission_manager", lambda: __import__(
        "app.core.permission_manager", fromlist=["PermissionManager"]).PermissionManager())
    ServiceProvider.register("task_pool", lambda: __import__(
        "app.core.task_pool", fromlist=["TaskPoolManager"]).TaskPoolManager())
    ServiceProvider.register("evaluation_service", lambda: __import__(
        "app.core.evaluation_service", fromlist=["AuditEvaluationService"]).AuditEvaluationService())
    ServiceProvider.register("prompt_registry", lambda: __import__(
        "app.core.prompt_service", fromlist=["PromptRegistryService"]).PromptRegistryService())

    # ── Skills ────────────────────────────────────────────────
    ServiceProvider.register("fast_router", lambda: __import__(
        "app.skills.fast_router", fromlist=["FastAuditRouter"]).FastAuditRouter())
    ServiceProvider.register("schema_injector", lambda: __import__(
        "app.skills.schema_injector", fromlist=["SchemaInjector"]).SchemaInjector())
    ServiceProvider.register("schema_manager", lambda: __import__(
        "app.skills.schema_manager", fromlist=["SchemaManager"]).SchemaManager())
    ServiceProvider.register("sql_validator", lambda: __import__(
        "app.skills.sql_validator", fromlist=["SQLLogicValidator"]).SQLLogicValidator())
    ServiceProvider.register("rule_engine", lambda: __import__(
        "app.skills.audit_rules", fromlist=["AuditRuleEngine"]).AuditRuleEngine())
    ServiceProvider.register("anomaly_detector", lambda: __import__(
        "app.skills.anomaly_algorithms", fromlist=["AnomalyAlgorithmEngine"]).AnomalyAlgorithmEngine())
    ServiceProvider.register("report_renderer", lambda: __import__(
        "app.reporting.report_renderer", fromlist=["AuditReportRenderer"]).AuditReportRenderer())

    # ── Memory ────────────────────────────────────────────────
    ServiceProvider.register("history_manager", lambda: __import__(
        "app.core.memory.history", fromlist=["HistoryManager"]).HistoryManager())
    ServiceProvider.register("session_store", lambda: __import__(
        "app.core.memory.session_store", fromlist=["SessionStore"]).SessionStore())
    ServiceProvider.register("experience_manager", lambda: __import__(
        "app.core.memory.experience", fromlist=["ExperienceManager"]).ExperienceManager())

    logger.info(f"[Bootstrap] {len(ServiceProvider.list_services())} services registered")
    logger.debug(f"[Bootstrap] Services: {ServiceProvider.list_services()}")
