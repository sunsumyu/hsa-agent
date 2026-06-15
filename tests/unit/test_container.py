"""
Smoke tests for the ServiceProvider DI container.
"""

import pytest
from app.core.container import ServiceProvider


class FakeService:
    def __init__(self):
        self.value = 42


class FakeManager:
    def __init__(self, dep=None):
        self.dep = dep


@pytest.fixture(autouse=True)
def clean_container():
    """Reset container state before and after each test."""
    ServiceProvider.reset()
    yield
    ServiceProvider.reset()


def test_register_and_resolve_class():
    ServiceProvider.register("fake", FakeService)
    svc = ServiceProvider.resolve("fake")
    assert isinstance(svc, FakeService)
    assert svc.value == 42


def test_lazy_creation():
    """Service should not be instantiated until first resolve."""
    ServiceProvider.register("fake", FakeService)
    assert "fake" not in ServiceProvider._instances
    ServiceProvider.resolve("fake")
    assert "fake" in ServiceProvider._instances


def test_singleton_caching():
    """Multiple resolve() calls should return the same instance."""
    ServiceProvider.register("fake", FakeService)
    a = ServiceProvider.resolve("fake")
    b = ServiceProvider.resolve("fake")
    assert a is b


def test_register_instance():
    svc = FakeService()
    ServiceProvider.register_instance("fake", svc)
    assert ServiceProvider.resolve("fake") is svc


def test_override():
    ServiceProvider.register("fake", FakeService)
    real = ServiceProvider.resolve("fake")
    mock = FakeService()
    ServiceProvider.override("fake", mock)
    assert ServiceProvider.resolve("fake") is mock
    assert ServiceProvider.resolve("fake") is not real


def test_reset_clears_override():
    ServiceProvider.register("fake", FakeService)
    ServiceProvider.override("fake", FakeService())
    ServiceProvider.reset("fake")
    # After reset, should lazily recreate from factory
    svc = ServiceProvider.resolve("fake")
    assert isinstance(svc, FakeService)


def test_try_resolve_returns_default():
    result = ServiceProvider.try_resolve("nonexistent", default="fallback")
    assert result == "fallback"


def test_resolve_unregistered_raises():
    with pytest.raises(KeyError):
        ServiceProvider.resolve("nonexistent")


def test_factory_callable():
    ServiceProvider.register("mgr", lambda: FakeManager(dep="test"))
    mgr = ServiceProvider.resolve("mgr")
    assert mgr.dep == "test"


def test_list_services():
    ServiceProvider.register("a", FakeService)
    ServiceProvider.register("b", FakeService)
    services = ServiceProvider.list_services()
    assert "a" in services
    assert "b" in services


def test_is_registered():
    assert not ServiceProvider.is_registered("fake")
    ServiceProvider.register("fake", FakeService)
    assert ServiceProvider.is_registered("fake")
