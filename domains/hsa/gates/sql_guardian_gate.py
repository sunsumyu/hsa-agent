"""
domains/hsa/gates/sql_guardian_gate.py
======================================
HSA SQL AST Security and dialect validation gate.
Implements the generic BaseSymbolicGate interface for ClickHouse medical audit SQL.
"""

from typing import Dict, Any
from cores.gates.base_gate import BaseSymbolicGate, GateResult
from app.skills.security.security import SQLGuardian, SecurityViolationError


class HSASQLGuardianGate(BaseSymbolicGate):
    """Deterministic neuro-symbolic gate verifying SQL AST safety and schema alignment."""

    def evaluate(self, state: Dict[str, Any]) -> GateResult:
        sql = state.get("sql") or state.get("query")
        if not sql:
            # Check sql_history if available
            sql_history = state.get("sql_history") or []
            if sql_history:
                last_item = sql_history[-1]
                sql = last_item.get("sql") if isinstance(last_item, dict) else str(last_item)

        if not sql:
            return GateResult(passed=True)

        try:
            SQLGuardian.validate_sql(sql)
            return GateResult(passed=True)
        except SecurityViolationError as e:
            return GateResult(
                passed=False,
                reason=f"HSA SQL Guardian violation: {str(e)}",
                error_code="SQL_SECURITY_VIOLATION",
                details={"sql": sql, "error": str(e)},
            )
        except Exception as e:
            return GateResult(
                passed=False,
                reason=f"HSA SQL validation error: {str(e)}",
                error_code="SQL_VALIDATION_ERROR",
                details={"sql": sql, "error": str(e)},
            )
