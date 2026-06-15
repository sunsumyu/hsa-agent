"""
app/core/container.py
=====================
[V211.0] Lightweight dependency injection container (ServiceProvider).

Solves the core architectural problem: 25+ module-level singletons are
instantiated at import time, making them impossible to mock in tests and
creating implicit import-order dependencies.

Design principles:
    - Lazy: services are created on first resolve(), not at registration.
    - Non-intrusive: existing module-level singletons stay as backward-compatible
      aliases that delegate to this container.
    - Testable: ServiceProvider.override() replaces any service for the
      duration of a test, then ServiceProvider.reset() restores it.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional
from loguru import logger


class ServiceProvider:
    """A minimal service locator / DI container."""

    _factories: Dict[str, Callable[[], Any]] = {}
    _instances: Dict[str, Any] = {}
    _overrides: Dict[str, Any] = {}

    @classmethod
    def register(cls, name: str, factory: Any) -> None:
        """Register a service with a class or zero-arg callable factory."""
        if isinstance(factory, type):
            cls._factories[name] = factory
        elif callable(factory):
            cls._factories[name] = factory
        else:
            raise TypeError(f"Factory for '{name}' must be a class or callable, got {type(factory)}")
        logger.debug(f"[DI] Registered service: {name}")

    @classmethod
    def register_instance(cls, name: str, instance: Any) -> None:
        """Register a pre-built singleton instance directly."""
        cls._instances[name] = instance
        logger.debug(f"[DI] Registered instance: {name}")

    @classmethod
    def resolve(cls, name: str) -> Any:
        """Resolve a service by name. Creates on first call, caches after."""
        if name in cls._overrides:
            return cls._overrides[name]
        if name in cls._instances:
            return cls._instances[name]
        if name in cls._factories:
            instance = cls._factories[name]()
            cls._instances[name] = instance
            return instance
        raise KeyError(f"Service '{name}' is not registered. Available: {sorted(cls._factories.keys())}")

    @classmethod
    def try_resolve(cls, name: str, default: Any = None) -> Any:
        """Non-throwing resolve, returns default if not found."""
        try:
            return cls.resolve(name)
        except KeyError:
            return default

    @classmethod
    def override(cls, name: str, mock_instance: Any) -> None:
        """Replace a service with a mock for testing."""
        cls._overrides[name] = mock_instance
        logger.debug(f"[DI] Override set: {name}")

    @classmethod
    def reset(cls, name: Optional[str] = None) -> None:
        """Clear overrides (and optionally cached instances). Call in test teardown."""
        if name:
            cls._overrides.pop(name, None)
            cls._instances.pop(name, None)
        else:
            cls._overrides.clear()
            cls._instances.clear()

    @classmethod
    def is_registered(cls, name: str) -> bool:
        return name in cls._factories or name in cls._instances

    @classmethod
    def list_services(cls) -> list:
        return sorted(set(list(cls._factories.keys()) + list(cls._instances.keys())))
