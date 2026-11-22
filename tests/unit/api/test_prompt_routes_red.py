"""
tests/unit/api/test_prompt_routes_red.py
========================================
Red unit tests for Prompt Manager API routes (app/routes/prompts.py).
Tests:
- GET /api/prompts/list
- GET /api/prompts/{prompt_id}/details
- POST /api/prompts/save
- GET /api/prompts/{prompt_id}/history
- GET /api/prompts/compare
- POST /api/prompts/rollback
"""

import pytest
from pathlib import Path
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.core.registry.prompt_version_manager import PromptVersionManager
import app.api.routes.prompts as prompts_module
from app.api.routes.prompts import router


@pytest.fixture
def isolated_client(tmp_path: Path, monkeypatch):
    test_prompts_dir = tmp_path / "prompts"
    test_prompts_dir.mkdir(parents=True, exist_ok=True)
    
    test_manager = PromptVersionManager(prompts_dir=test_prompts_dir)
    # Monkeypatch the module-level prompt_version_manager
    monkeypatch.setattr(prompts_module, "prompt_version_manager", test_manager)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app), test_manager


def test_list_and_details_prompts(isolated_client):
    client, manager = isolated_client

    # Initially empty
    resp = client.get("/api/prompts/list")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["prompts"] == []

    # Save a prompt first
    manager.save_prompt_version(
        prompt_id="TESTER",
        version="1.0.0",
        description="A test prompt",
        system_template="You are a test agent."
    )

    # Now list again
    resp2 = client.get("/api/prompts/list")
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["ok"] is True
    assert len(data["prompts"]) == 1
    assert data["prompts"][0]["id"] == "TESTER"
    assert data["prompts"][0]["version"] == "1.0.0"

    # Get details
    resp_details = client.get("/api/prompts/TESTER/details")
    assert resp_details.status_code == 200
    det = resp_details.json()
    assert det["ok"] is True
    assert det["data"]["id"] == "TESTER"
    assert det["data"]["version"] == "1.0.0"
    assert det["data"]["system_template"] == "You are a test agent."

    # Get details for non-existent
    resp_404 = client.get("/api/prompts/UNKNOWN_PROMPT/details")
    assert resp_404.status_code == 404
    assert resp_404.json()["ok"] is False


def test_save_and_history(isolated_client):
    client, manager = isolated_client

    # Save v1.0.0 via POST API
    payload1 = {
        "prompt_id": "AUDIT_PROMPT",
        "version": "1.0.0",
        "description": "Initial audit prompt",
        "system_template": "Audit system prompt v1",
        "variables": ["var1"],
        "has_messages_placeholder": True
    }
    resp1 = client.post("/api/prompts/save", json=payload1)
    assert resp1.status_code == 200
    assert resp1.json()["ok"] is True

    # Save v1.1.0 via POST API
    payload2 = {
        "prompt_id": "AUDIT_PROMPT",
        "version": "1.1.0",
        "description": "Updated audit prompt",
        "system_template": "Audit system prompt v1.1",
        "variables": ["var1", "var2"],
        "has_messages_placeholder": True
    }
    resp2 = client.post("/api/prompts/save", json=payload2)
    assert resp2.status_code == 200
    assert resp2.json()["ok"] is True

    # Check history
    resp_hist = client.get("/api/prompts/AUDIT_PROMPT/history")
    assert resp_hist.status_code == 200
    hist = resp_hist.json()
    assert hist["ok"] is True
    assert len(hist["history"]) >= 2
    versions = [h["version"] for h in hist["history"]]
    assert "1.0.0" in versions
    assert "1.1.0" in versions


def test_compare_and_rollback(isolated_client):
    client, manager = isolated_client

    # Setup two versions
    manager.save_prompt_version("COMPARE_P", "1.0.0", "v1 desc", "Template v1")
    manager.save_prompt_version("COMPARE_P", "2.0.0", "v2 desc", "Template v2")

    # Compare
    resp_comp = client.get("/api/prompts/compare", params={
        "prompt_id": "COMPARE_P",
        "version_a": "1.0.0",
        "version_b": "2.0.0"
    })
    assert resp_comp.status_code == 200
    comp_data = resp_comp.json()
    assert comp_data["ok"] is True
    assert comp_data["template_a"] == "Template v1"
    assert comp_data["template_b"] == "Template v2"

    # Compare non-existent versions
    resp_comp_404 = client.get("/api/prompts/compare", params={
        "prompt_id": "COMPARE_P",
        "version_a": "1.0.0",
        "version_b": "9.9.9"
    })
    assert resp_comp_404.status_code == 404

    # Rollback to v1.0.0
    resp_rb = client.post("/api/prompts/rollback", json={
        "prompt_id": "COMPARE_P",
        "target_version": "1.0.0"
    })
    assert resp_rb.status_code == 200
    assert resp_rb.json()["ok"] is True

    # Active file should now be 1.0.0
    resp_det = client.get("/api/prompts/COMPARE_P/details")
    assert resp_det.status_code == 200
    assert resp_det.json()["data"]["version"] == "1.0.0"
    assert resp_det.json()["data"]["system_template"] == "Template v1"

    # Rollback to non-existent
    resp_rb_404 = client.post("/api/prompts/rollback", json={
        "prompt_id": "COMPARE_P",
        "target_version": "9.9.9"
    })
    assert resp_rb_404.status_code == 404
