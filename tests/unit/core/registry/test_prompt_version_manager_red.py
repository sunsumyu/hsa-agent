"""
tests/unit/core/registry/test_prompt_version_manager_red.py
===========================================================
Red unit tests for PromptVersionManager deep module.
Tests:
- save_prompt_version (initial save and automatic history archiving)
- get_prompt_history (listing historical versions sorted)
- rollback_prompt_version (rolling back to previous version with backup)
- compare_prompt_versions (diffing templates across two versions)
- list_prompt_summaries (aggregating current prompts with history count)
"""

import pytest
import yaml
from pathlib import Path

from app.core.registry.prompt_version_manager import PromptVersionManager


@pytest.fixture
def temp_prompts_dir(tmp_path: Path) -> Path:
    p_dir = tmp_path / "prompts"
    p_dir.mkdir(parents=True, exist_ok=True)
    return p_dir


def test_save_and_archive_history(temp_prompts_dir: Path):
    manager = PromptVersionManager(prompts_dir=temp_prompts_dir)

    # 1. First save: v1.0.0
    res1 = manager.save_prompt_version(
        prompt_id="PLANNER",
        version="1.0.0",
        description="Initial planner prompt",
        system_template="You are a medical planner."
    )
    assert res1["ok"] is True
    active_file = temp_prompts_dir / "planner.yaml"
    assert active_file.exists()

    # 2. Second save: v1.1.0 (should archive v1.0.0 into history/planner_v1.0.0.yaml)
    res2 = manager.save_prompt_version(
        prompt_id="PLANNER",
        version="1.1.0",
        description="Updated planner prompt with cross validation",
        system_template="You are an advanced medical planner."
    )
    assert res2["ok"] is True

    history_dir = temp_prompts_dir / "history"
    assert (history_dir / "planner_v1.0.0.yaml").exists()
    assert (history_dir / "planner_v1.1.0.yaml").exists()

    # Active file has v1.1.0 content
    with open(active_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data["version"] == "1.1.0"
    assert "advanced" in data["system_template"]


def test_get_prompt_history(temp_prompts_dir: Path):
    manager = PromptVersionManager(prompts_dir=temp_prompts_dir)
    manager.save_prompt_version("CODER", "1.0.0", "v1", "Template v1")
    manager.save_prompt_version("CODER", "1.1.0", "v2", "Template v2")

    history = manager.get_prompt_history("CODER")
    assert len(history) >= 2
    versions = [h["version"] for h in history]
    assert "1.0.0" in versions
    assert "1.1.0" in versions


def test_rollback_prompt_version(temp_prompts_dir: Path):
    manager = PromptVersionManager(prompts_dir=temp_prompts_dir)
    manager.save_prompt_version("AUDITOR", "1.0.0", "initial", "Auditor v1 template")
    manager.save_prompt_version("AUDITOR", "2.0.0", "broken", "Auditor v2 broken template")

    # Rollback to 1.0.0
    res = manager.rollback_prompt_version("AUDITOR", "1.0.0")
    assert res["ok"] is True

    # Active file should now have 1.0.0
    active_file = temp_prompts_dir / "auditor.yaml"
    with open(active_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data["version"] == "1.0.0"
    assert data["system_template"] == "Auditor v1 template"

    # Rollback to non-existent version raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        manager.rollback_prompt_version("AUDITOR", "9.9.9")


def test_compare_prompt_versions(temp_prompts_dir: Path):
    manager = PromptVersionManager(prompts_dir=temp_prompts_dir)
    manager.save_prompt_version("REPORTER", "1.0.0", "v1 desc", "Reporter template A")
    manager.save_prompt_version("REPORTER", "2.0.0", "v2 desc", "Reporter template B")

    diff = manager.compare_prompt_versions("REPORTER", "1.0.0", "2.0.0")
    assert diff["ok"] is True
    assert diff["template_a"] == "Reporter template A"
    assert diff["template_b"] == "Reporter template B"
    assert diff["desc_a"] == "v1 desc"
    assert diff["desc_b"] == "v2 desc"


def test_list_prompt_summaries(temp_prompts_dir: Path):
    manager = PromptVersionManager(prompts_dir=temp_prompts_dir)
    manager.save_prompt_version("TOOL_A", "1.0.0", "Tool A", "Template A")
    manager.save_prompt_version("TOOL_B", "1.0.0", "Tool B", "Template B")

    summaries = manager.list_prompt_summaries()
    assert len(summaries) == 2
    ids = [s["id"] for s in summaries]
    assert "TOOL_A" in ids
    assert "TOOL_B" in ids
