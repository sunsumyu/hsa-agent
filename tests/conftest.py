"""
tests/conftest.py
=================
Global pytest fixtures and test environment bootstrap.
Ensures ServiceProvider has default service definitions available for all test suites.
Implements Matt Pocock's Two-Adapter Rule (InMemoryObservabilityFake) for zero-network testing.
"""

from typing import Dict, Any, List, Optional
from contextlib import contextmanager
import pytest
from app.core.bootstrap import register_services
from app.core.container import ServiceProvider
from app.core.observability_service import sanitize_pii_payload


class InMemoryObservabilityFake:
    """
    [Matt Pocock Two-Adapter Rule]
    用于单元测试的内存 Fake 适配器：零网络探测、零外部依赖、记录操作以供断言。
    """
    def __init__(self):
        self.recorded_feedbacks: List[Dict[str, Any]] = []
        self.closed: bool = False
        self._langsmith_client = None

    def _sanitize_pii(self, val: Any) -> Any:
        return sanitize_pii_payload(val)

    def get_stream_callbacks(self) -> List[Any]:
        return []

    def configure_run(
        self,
        node_name: str,
        session_id: str,
        extra_meta: Optional[Dict[str, Any]] = None,
        base_config: Optional[Any] = None
    ) -> Dict[str, Any]:
        cfg = (base_config or {}).copy()
        cfg["callbacks"] = []
        cfg["metadata"] = {
            "node": node_name,
            "session_id": session_id,
            "user_id": session_id,
            **(extra_meta or {})
        }
        return cfg

    def record_feedback(
        self,
        run_id: str,
        score: float,
        category: Optional[str] = None,
        comment: Optional[str] = None
    ) -> bool:
        self.recorded_feedbacks.append({
            "run_id": run_id,
            "score": score,
            "category": category,
            "comment": comment
        })
        return True

    @contextmanager
    def node_scope(self, node_name: str, session_id: str, state: Dict[str, Any]):
        yield {
            "langgraph_node": node_name,
            "session_id": session_id,
            "retry_count": state.get("retry_count", 0),
            "phase": "audit_execution"
        }

    def shutdown(self) -> None:
        self.closed = True


@pytest.fixture(scope="session", autouse=True)
def setup_test_di():
    """Ensure DI container has services registered for all tests and observability initialized."""
    register_services()
