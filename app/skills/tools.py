"""
app/skills/tools.py
===================
[Phase 3.2] Backward-compatible re-export hub.

This module was split into four focused submodules:
  - sql_tools.py      SQL execution, sanitization, auto-healing
  - schema_tools.py   Schema lookup, governance, knowledge, calculator
  - analysis_tools.py Rule engine, anomaly detection, graph queries
  - memory_tools.py   Memory management, notes, embeddings

Everything is re-exported here so existing imports
(`from app.tools import execute_audit_sql`, `inspect.getmembers(tools_mod)`,
etc.) continue to work without changes.
"""

# SQL execution core
from app.skills.sql_tools import (
    _sanitize_results,
    _execute_audit_sql_logic,
    _heal_group_by_215,
    execute_audit_sql,
)

# Schema, governance, knowledge, calculator
from app.skills.schema_tools import (
    list_tables,
    get_table_schema,
    calculator,
    check_audit_governance,
    lookup_medical_schema,
    _load_expert_kb,
    search_expert_knowledge,
    expand_medical_codes,
)

# Rule engine, anomaly detection, graph analysis
from app.skills.analysis_tools import (
    audit_medical_rule,
    run_anomaly_detection,
    ingest_knowledge_document,
    query_knowledge_base,
    query_fraud_ring,
    federated_graph_sideloader,
)

# Memory, notes, embeddings
from app.skills.memory_tools import (
    manage_memory,
    write_audit_note,
    write_audit_notes,
    read_all_audit_notes,
    clear_audit_notes,
    get_embeddings,
)

__all__ = [
    # SQL
    "execute_audit_sql",
    "_execute_audit_sql_logic",
    "_sanitize_results",
    "_heal_group_by_215",
    # Schema
    "list_tables",
    "get_table_schema",
    "calculator",
    "check_audit_governance",
    "lookup_medical_schema",
    "search_expert_knowledge",
    "expand_medical_codes",
    # Analysis
    "audit_medical_rule",
    "run_anomaly_detection",
    "ingest_knowledge_document",
    "query_knowledge_base",
    "query_fraud_ring",
    "federated_graph_sideloader",
    # Memory
    "manage_memory",
    "write_audit_note",
    "write_audit_notes",
    "read_all_audit_notes",
    "clear_audit_notes",
    "get_embeddings",
]
