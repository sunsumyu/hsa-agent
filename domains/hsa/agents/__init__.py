"""
domains/hsa/agents
==================
HSA Domain-Specific Multi-Agent Roles:
- CoderAgent / AuditCoderAgent: ClickHouse SQL generator with self-healing tool execution
- PlannerAgent / AuditPlannerAgent: Medical audit intent decomposition and table routing
- ReflectionAgent / AuditReflectionAgent: Quality gating and error diagnosis
- ConsolidatorAgent / AuditConsolidatorAgent: Experience mining and knowledge distillation
"""

from app.agents.coder_agent import AuditCoderAgent, coder_agent
from app.agents.planner_agent import AuditPlannerAgent, planner_agent
from app.agents.reflection_agent import AuditReflectionAgent, reflection_agent
from app.agents.consolidator_agent import AuditConsolidatorAgent, consolidator_agent

# Standardized aliases
CoderAgent = AuditCoderAgent
PlannerAgent = AuditPlannerAgent
ReflectionAgent = AuditReflectionAgent
ConsolidatorAgent = AuditConsolidatorAgent

__all__ = [
    "AuditCoderAgent",
    "AuditPlannerAgent",
    "AuditReflectionAgent",
    "AuditConsolidatorAgent",
    "CoderAgent",
    "PlannerAgent",
    "ReflectionAgent",
    "ConsolidatorAgent",
    "coder_agent",
    "planner_agent",
    "reflection_agent",
    "consolidator_agent",
]
