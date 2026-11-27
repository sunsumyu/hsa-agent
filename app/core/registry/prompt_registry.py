"""
app.core.registry.prompt_registry — 版本化 Prompt 注册器
==================================================
从 YAML 文件加载 Prompt, 支持:
  - 版本追踪 (version + content_hash)
  - 热加载 (reload)
  - 与 Langfuse 云端管理集成 (优先云端, 本地 fallback)
  - 回溯审计: 每次调用记录使用的 prompt_id + version
"""

from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from loguru import logger


_REPO_ROOT = next(
    (p for p in Path(__file__).resolve().parents if (p / "configs").is_dir()),
    Path(__file__).resolve().parent.parent.parent.parent,
)
_PROMPTS_DIR = _REPO_ROOT / "configs" / "prompts"


class PromptEntry:
    """单个 Prompt 的元数据 + 模板。"""

    def __init__(self, prompt_id: str, data: Dict[str, Any]):
        self.prompt_id = prompt_id
        self.version: str = data.get("version", "0.0.0")
        self.description: str = data.get("description", "")
        self.system_template: str = data["system_template"]
        self.variables: list = data.get("variables", [])
        self.has_messages_placeholder: bool = data.get("has_messages_placeholder", True)
        self.human_suffix: Optional[str] = data.get("human_suffix")
        self.content_hash: str = hashlib.sha256(
            self.system_template.encode("utf-8")
        ).hexdigest()[:12]
        self._compiled: Optional[ChatPromptTemplate] = None

    def compile(self) -> ChatPromptTemplate:
        """编译为 LangChain ChatPromptTemplate (带缓存)。"""
        if self._compiled is not None:
            return self._compiled

        messages = [("system", self.system_template)]
        if self.has_messages_placeholder:
            messages.append(MessagesPlaceholder(variable_name="messages"))
        if self.human_suffix:
            messages.append(("human", self.human_suffix))

        self._compiled = ChatPromptTemplate.from_messages(messages)
        return self._compiled

    def __repr__(self) -> str:
        return f"<Prompt {self.prompt_id} v{self.version} hash={self.content_hash}>"


class PromptRegistry:
    """YAML-based Prompt 注册表。

    并发契约: 双重检查锁 + 局部构建整体替换 (与 SchemaRegistry 同款)。
    缓存引用只被原子替换、从不清空; reload 由提示词版本管理的 save/rollback
    端点触发, 运行中的每次 LLM 调用都要 get_entry, 不允许出现清空窗口。
    """

    def __init__(self, prompts_dir: Optional[Path] = None):
        self._dir = prompts_dir or _PROMPTS_DIR
        self._cache: Dict[str, PromptEntry] = {}
        self._loaded = False
        self._lock = threading.Lock()

    # ── 公共 API ──────────────────────────────────────────────

    def get(self, prompt_id: str) -> ChatPromptTemplate:
        """获取编译后的 ChatPromptTemplate。"""
        entry = self.get_entry(prompt_id)
        return entry.compile()

    def get_entry(self, prompt_id: str) -> PromptEntry:
        """获取 PromptEntry (含元数据)。"""
        self._ensure_loaded()
        cache = self._cache  # 引用快照读: 加载方只整体替换, 本地引用始终完整
        if prompt_id not in cache:
            raise KeyError(
                f"Prompt '{prompt_id}' not found. "
                f"Available: {list(cache.keys())}"
            )
        return cache[prompt_id]

    def get_version_info(self, prompt_id: str) -> Dict[str, str]:
        """返回版本信息, 供评测链路记录。"""
        entry = self.get_entry(prompt_id)
        return {
            "prompt_id": entry.prompt_id,
            "version": entry.version,
            "content_hash": entry.content_hash,
        }

    def list_prompts(self) -> list:
        """列出所有已注册的 prompt_id。"""
        self._ensure_loaded()
        return list(self._cache.keys())

    def reload(self) -> None:
        """强制重新加载所有 YAML 文件。

        与首次加载共用同一把锁; 先在锁内构建完整新缓存再整体替换引用。
        旧实现先 _cache.clear() 再重载, clear 窗口内 get_entry 直接 KeyError。
        """
        with self._lock:
            self._cache = self._load_all()
            self._loaded = True
        logger.info(f"[PromptRegistry] Reloaded {len(self._cache)} prompts from {self._dir}")

    # ── 内部逻辑 ──────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        """惰性加载守卫 (双重检查锁)。

        快路径无锁读 _loaded, 已加载则零开销返回; 仅在未命中时加锁,
        并在锁内二次检查, 保证并发首次调用只真正执行一次加载,
        且加载期间不会向共享缓存边写边被迭代。
        """
        if self._loaded:
            return

        with self._lock:
            if self._loaded:
                return
            self._cache = self._load_all()
            self._loaded = True
        logger.info(
            f"[PromptRegistry] Initialized with {len(self._cache)} prompts "
            f"from {self._dir}"
        )

    def _load_all(self) -> Dict[str, PromptEntry]:
        """实际加载逻辑; 调用方必须持有 self._lock。构建局部缓存并整体返回。"""
        cache: Dict[str, PromptEntry] = {}

        if not self._dir.exists():
            logger.warning(f"[PromptRegistry] Prompts directory not found: {self._dir}")
            return cache

        for yaml_file in sorted(self._dir.glob("*.yaml")):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if not data or "system_template" not in data:
                    logger.warning(f"[PromptRegistry] Skipping invalid file: {yaml_file.name}")
                    continue
                prompt_id = data.get("id", yaml_file.stem)
                entry = PromptEntry(prompt_id, data)
                cache[prompt_id] = entry
                logger.debug(f"[PromptRegistry] Loaded {entry}")
            except Exception as e:
                logger.error(f"[PromptRegistry] Failed to load {yaml_file.name}: {e}")

        return cache


# 模块级单例
prompt_registry = PromptRegistry()
