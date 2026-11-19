"""
app/core/registry/prompt_version_manager.py
===========================================
提示词版本归档、历史演进与差异对比管理器（Deep Module）

核心职责：
1. 提示词文件解析与元数据安全提取
2. 版本演进自动快照与历史文件安全归档（防重复覆盖）
3. 提示词历史版本回滚与当前活动版本自动暂存保护
4. 双版本系统模板与配置差异比对
5. 注册表动态热重载通知
"""

from __future__ import annotations

import hashlib
import os
import yaml
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
from loguru import logger

_REPO_ROOT = next(
    (p for p in Path(__file__).resolve().parents if (p / "configs").is_dir()),
    Path(__file__).resolve().parent.parent.parent.parent,
)
_DEFAULT_PROMPTS_DIR = _REPO_ROOT / "configs" / "prompts"


class PromptVersionManager:
    """提示词版本与历史管理器。"""

    def __init__(self, prompts_dir: Optional[Path] = None):
        self._dir = prompts_dir or _DEFAULT_PROMPTS_DIR
        self._history_dir = self._dir / "history"
        self._history_dir.mkdir(parents=True, exist_ok=True)

    @property
    def prompts_dir(self) -> Path:
        return self._dir

    @property
    def history_dir(self) -> Path:
        return self._history_dir

    def get_history_files(self, prompt_id: str) -> List[Path]:
        """获取指定提示词的所有历史文件列表（按修改时间倒序排列）。"""
        pattern = f"{prompt_id.lower()}_v*.yaml"
        files = list(self.history_dir.glob(pattern))
        files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return files

    def parse_yaml_file(self, file_path: Path) -> Dict[str, Any]:
        """安全解析一个 YAML 文件并返回其元数据。"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            system_template = data.get("system_template", "")
            content_hash = (
                hashlib.sha256(system_template.encode("utf-8")).hexdigest()[:12]
                if system_template
                else ""
            )
            return {
                "id": data.get("id", file_path.stem.split("_v")[0].upper()),
                "version": str(data.get("version", "0.0.0")),
                "description": data.get("description", ""),
                "variables": data.get("variables", []),
                "has_messages_placeholder": data.get("has_messages_placeholder", True),
                "system_template": system_template,
                "human_suffix": data.get("human_suffix"),
                "content_hash": content_hash,
                "last_modified": datetime.fromtimestamp(file_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "file_size": file_path.stat().st_size,
            }
        except Exception as e:
            logger.error(f"[PromptVersionManager] 无法解析 YAML 文件 {file_path.name}: {e}")
            return {}

    def list_prompt_summaries(self) -> List[Dict[str, Any]]:
        """获取当前所有提示词的最新版本及其基本元数据列表。"""
        # 扫描 prompts_dir 下的所有 .yaml 文件（排除 history 目录）
        yaml_files = [f for f in self._dir.glob("*.yaml") if f.is_file()]
        summaries: List[Dict[str, Any]] = []

        for yf in sorted(yaml_files, key=lambda x: x.name):
            data = self.parse_yaml_file(yf)
            if not data:
                continue
            pid = data["id"]
            hist_count = len(self.get_history_files(pid))
            summaries.append({
                "id": pid,
                "version": data["version"],
                "description": data["description"],
                "variables": data["variables"],
                "has_messages_placeholder": data["has_messages_placeholder"],
                "human_suffix": data["human_suffix"],
                "content_hash": data["content_hash"],
                "history_count": hist_count,
                "last_modified": data["last_modified"],
                "file_size": data["file_size"],
            })

        return summaries

    def get_prompt_details(self, prompt_id: str) -> Dict[str, Any]:
        """获取单个提示词的详细内容和完整参数。"""
        pid = prompt_id.lower()
        active_file = self._dir / f"{pid}.yaml"
        if not active_file.exists():
            raise KeyError(f"未找到提示词 {prompt_id}")

        data = self.parse_yaml_file(active_file)
        if not data:
            raise ValueError(f"提示词文件格式损坏: {active_file.name}")
        return data

    def get_prompt_history(self, prompt_id: str) -> List[Dict[str, Any]]:
        """获取指定提示词的完整历史版本列表。"""
        pid = prompt_id.lower()
        files = self.get_history_files(pid)
        history = []
        for f in files:
            p_data = self.parse_yaml_file(f)
            if p_data:
                history.append(p_data)
        return history

    def save_prompt_version(
        self,
        prompt_id: str,
        version: str,
        description: str,
        system_template: str,
        variables: Optional[List[str]] = None,
        has_messages_placeholder: bool = True,
        human_suffix: Optional[str] = None,
    ) -> Dict[str, Any]:
        """保存新版本的提示词，同时将旧版本归档至历史记录。"""
        pid = prompt_id.lower()
        active_file = self._dir / f"{pid}.yaml"

        # 1. 备份当前活动文件到历史目录中（如果存在的话）
        if active_file.exists():
            old_data = self.parse_yaml_file(active_file)
            old_ver = old_data.get("version", "0.0.0")
            backup_file = self._history_dir / f"{pid}_v{old_ver}.yaml"
            if not backup_file.exists():
                with open(backup_file, "w", encoding="utf-8") as f:
                    with open(active_file, "r", encoding="utf-8") as rf:
                        f.write(rf.read())
                logger.info(f"💾 [PromptVersionManager] 成功归档老版本 {old_ver} 到历史文件: {backup_file.name}")

        # 2. 写入新版本到活动文件
        new_content: Dict[str, Any] = {
            "id": prompt_id.upper(),
            "version": str(version),
            "description": description,
            "variables": variables or [],
            "has_messages_placeholder": has_messages_placeholder,
            "system_template": system_template,
        }
        if human_suffix is not None:
            new_content["human_suffix"] = human_suffix

        with open(active_file, "w", encoding="utf-8") as f:
            yaml.dump(new_content, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

        # 3. 同时将新版本写入历史文件夹做快照
        new_backup_file = self._history_dir / f"{pid}_v{version}.yaml"
        with open(new_backup_file, "w", encoding="utf-8") as f:
            yaml.dump(new_content, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

        # 4. 尝试热重载 prompt_registry
        try:
            from app.core.registry.prompt_registry import prompt_registry
            prompt_registry.reload()
        except Exception as e:
            logger.debug(f"[PromptVersionManager] 忽略提示词热重载通知: {e}")

        return {
            "ok": True,
            "message": f"成功保存提示词 {prompt_id.upper()} 新版本 {version}，已同步热重载！",
        }

    def rollback_prompt_version(self, prompt_id: str, target_version: str) -> Dict[str, Any]:
        """回滚提示词至指定的历史版本。"""
        pid = prompt_id.lower()
        history_file = self._history_dir / f"{pid}_v{target_version}.yaml"
        if not history_file.exists():
            raise FileNotFoundError(f"未找到历史版本文件: {pid}_v{target_version}.yaml")

        active_file = self._dir / f"{pid}.yaml"

        # 1. 备份当前活动文件
        if active_file.exists():
            curr_data = self.parse_yaml_file(active_file)
            curr_ver = curr_data.get("version", "0.0.0")
            curr_backup = self._history_dir / f"{pid}_v{curr_ver}.yaml"
            if not curr_backup.exists():
                with open(curr_backup, "w", encoding="utf-8") as f:
                    with open(active_file, "r", encoding="utf-8") as rf:
                        f.write(rf.read())

        # 2. 将历史版本文件复制到活动文件
        with open(active_file, "w", encoding="utf-8") as f:
            with open(history_file, "r", encoding="utf-8") as hf:
                f.write(hf.read())

        # 3. 尝试热重载 prompt_registry
        try:
            from app.core.registry.prompt_registry import prompt_registry
            prompt_registry.reload()
        except Exception as e:
            logger.debug(f"[PromptVersionManager] 忽略提示词热重载通知: {e}")

        return {
            "ok": True,
            "message": f"成功将提示词 {prompt_id.upper()} 回滚至历史版本 {target_version}！",
        }

    def compare_prompt_versions(self, prompt_id: str, version_a: str, version_b: str) -> Dict[str, Any]:
        """获取两个版本的系统提示模板与元数据，用于差异对比。"""
        pid = prompt_id.lower()
        file_a = self._history_dir / f"{pid}_v{version_a}.yaml"
        file_b = self._history_dir / f"{pid}_v{version_b}.yaml"
        active_file = self._dir / f"{pid}.yaml"

        data_a = None
        data_b = None

        if file_a.exists():
            data_a = self.parse_yaml_file(file_a)
        elif active_file.exists():
            act = self.parse_yaml_file(active_file)
            if act.get("version") == version_a:
                data_a = act

        if file_b.exists():
            data_b = self.parse_yaml_file(file_b)
        elif active_file.exists():
            act = self.parse_yaml_file(active_file)
            if act.get("version") == version_b:
                data_b = act

        if not data_a or not data_b:
            raise FileNotFoundError("未能找到指定版本的比对文件，请确保版本号正确且已存在历史记录中。")

        return {
            "ok": True,
            "prompt_id": prompt_id.upper(),
            "version_a": version_a,
            "version_b": version_b,
            "template_a": data_a.get("system_template", ""),
            "template_b": data_b.get("system_template", ""),
            "desc_a": data_a.get("description", ""),
            "desc_b": data_b.get("description", ""),
        }


# 全局默认单例
prompt_version_manager = PromptVersionManager()
