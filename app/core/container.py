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

import threading
from typing import Any, Callable, Dict, Optional
from loguru import logger


class ServiceProvider:
    """A minimal service locator / DI container."""

    _factories: Dict[str, Callable[[], Any]] = {}
    _instances: Dict[str, Any] = {}
    _overrides: Dict[str, Any] = {}
    # [P0-2] 类级互斥锁: resolve 的 check-construct-assign 必须原子,
    # 否则并发首次解析 (LazyProxy 每次属性访问都走 resolve) 会各自执行工厂
    # → 双实例: 各持独立状态互相覆盖, 持连接资源双份泄漏。
    # 用 RLock 而非 Lock: 工厂可能在锁内回调 resolve() 解析依赖 (同线程重入必须放行)。
    _lock = threading.RLock()

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
        """Resolve a service by name. Creates on first call, caches after.

        双重检查锁: 快路径无锁读缓存, 已命中零开销返回; 未命中时持锁二次检查
        后再构建, 保证并发首次解析只创建一个实例。
        """
        if name in cls._overrides:
            return cls._overrides[name]
        if name in cls._instances:
            return cls._instances[name]
        with cls._lock:
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
    def clear_overrides(cls, name: Optional[str] = None) -> None:
        """Clear test overrides without disturbing singleton instances or registered factories."""
        if name:
            cls._overrides.pop(name, None)
        else:
            cls._overrides.clear()
        logger.debug(f"[DI] Overrides cleared (target: {name or 'all'})")

    @classmethod
    def clear_instances(cls, name: Optional[str] = None) -> None:
        """Clear cached singleton instances so next resolve() reconstructs them."""
        if name:
            cls._instances.pop(name, None)
        else:
            cls._instances.clear()
        logger.debug(f"[DI] Instances cleared (target: {name or 'all'})")

    @classmethod
    def dispose_all(cls) -> None:
        """
        Gracefully dispose all active singleton services by calling close(), dispose(), or shutdown().
        Invoked during application lifespan shutdown or test suite cleanup.
        """
        for name, inst in list(cls._instances.items()):
            for method_name in ("close", "dispose", "shutdown", "aclose"):
                method = getattr(inst, method_name, None)
                if callable(method):
                    try:
                        logger.debug(f"[DI] Disposing service '{name}' via .{method_name}()")
                        res = method()
                        # If asynchronous, schedule or log
                        import inspect
                        if inspect.iscoroutine(res):
                            import asyncio
                            try:
                                loop = asyncio.get_event_loop()
                                if loop.is_running():
                                    asyncio.create_task(res)
                            except Exception:
                                pass
                    except Exception as e:
                        logger.warning(f"[DI] Error while disposing service '{name}': {e}")
                    break
        cls._instances.clear()

    @classmethod
    def get_status(cls) -> Dict[str, Dict[str, Any]]:
        """Return diagnostic status matrix of all registered and instantiated services."""
        all_names = sorted(set(list(cls._factories.keys()) + list(cls._instances.keys())))
        status_map: Dict[str, Dict[str, Any]] = {}
        for name in all_names:
            is_active = name in cls._instances
            is_overridden = name in cls._overrides
            inst = cls._instances.get(name)
            type_name = type(inst).__name__ if inst is not None else "LazyPending"
            status_map[name] = {
                "status": "active" if is_active else "pending",
                "is_overridden": is_overridden,
                "type": type_name,
            }
        return status_map

    @classmethod
    def reset(cls, name: Optional[str] = None) -> None:
        """Clear overrides, cached instances, and registered factories. Call in test teardown."""
        if name:
            cls._overrides.pop(name, None)
            cls._instances.pop(name, None)
            cls._factories.pop(name, None)
        else:
            cls._overrides.clear()
            cls._instances.clear()
            cls._factories.clear()

    @classmethod
    def is_registered(cls, name: str) -> bool:
        return name in cls._factories or name in cls._instances

    @classmethod
    def list_services(cls) -> list:
        return sorted(set(list(cls._factories.keys()) + list(cls._instances.keys())))


class LazyProxy:
    """
    [Matt Pocock Deep Module] 动态穿透服务代理 (Dynamic Transparent Proxy)
    - 当 ServiceProvider.override 发生时，代理立即且无缝穿透至 Mock 实例
    - 代理自身不持有单例缓存，单例缓存统一由 ServiceProvider 生命周期管理
    - 支持优雅降级 fallback_factory 与自愈式按需引导
    """
    def __init__(self, name: str, fallback_factory: Optional[Callable[[], Any]] = None):
        self._name = name
        self._fallback_factory = fallback_factory

    def _get_instance(self) -> Any:
        # 1. 优先检查并穿透 ServiceProvider 中的 override
        if self._name in ServiceProvider._overrides:
            return ServiceProvider._overrides[self._name]

        # 2. 从 ServiceProvider 正常解析 (自带 O(1) 单例实例缓存)
        try:
            return ServiceProvider.resolve(self._name)
        except KeyError:
            if self._fallback_factory is not None:
                return self._fallback_factory()
            try:
                from app.core.bootstrap import register_services
                register_services()
                return ServiceProvider.resolve(self._name)
            except Exception:
                raise

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get_instance(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            setattr(self._get_instance(), name, value)

    def __delattr__(self, name: str) -> None:
        # 与 __getattr__/__setattr__ 保持语义对称：非私有属性删除同样穿透至真实实例。
        # 缺失此协议会让 patch.object(LazyProxy, ...) 在退出时 delattr 代理壳自身而崩溃。
        if name.startswith("_"):
            super().__delattr__(name)
        else:
            delattr(self._get_instance(), name)

    def __call__(self, *args, **kwargs) -> Any:
        return self._get_instance()(*args, **kwargs)
