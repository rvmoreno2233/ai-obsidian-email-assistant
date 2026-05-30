"""Tests for Studio Email Settings API routes and background poller."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.email_rules import (
    EmailRulesCatalog,
    ResponseTemplatesCatalog,
    save_rules,
    save_templates,
)
from app.response_queue import PollerState, QueueEntry, ResponseQueueStore
from app.web import app as web_app
from app.web.poller import BackgroundPoller


@pytest.fixture
def studio_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """TestClient with isolated queue/rules/templates and poller disabled."""
    rules_path = tmp_path / "email_rules.yaml"
    templates_path = tmp_path / "response_templates.yaml"
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir()

    save_rules(EmailRulesCatalog(), rules_path)
    save_templates(ResponseTemplatesCatalog(), templates_path)

    store = ResponseQueueStore(queue_dir)
    poller = BackgroundPoller(queue_store=store, interval_seconds=60)
    poller.save_state(PollerState(enabled=False, interval_seconds=60))

    monkeypatch.setattr(web_app, "_queue_store", store)
    monkeypatch.setattr(web_app, "_poller", poller)
    monkeypatch.setattr("app.email_rules.EMAIL_RULES_FILE", rules_path)
    monkeypatch.setattr("app.email_rules.RESPONSE_TEMPLATES_FILE", templates_path)

    with TestClient(web_app.app) as client:
        yield client, store, rules_path, templates_path


def test_ollama_health_mocked(studio_client, monkeypatch: pytest.MonkeyPatch):
    client, _, _, _ = studio_client
    mock_client = MagicMock()
    mock_client.health_check.return_value = {
        "ok": True,
        "model": "llama3.1",
        "host": "http://127.0.0.1:11434",
        "models_available": ["llama3.1"],
    }
    monkeypatch.setattr(web_app, "OllamaClient", lambda: mock_client)

    response = client.get("/api/ollama/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_ollama_test_mocked(studio_client, monkeypatch: pytest.MonkeyPatch):
    client, _, _, _ = studio_client
    mock_client = MagicMock()
    mock_client.chat_text.return_value = "ok"
    monkeypatch.setattr(web_app, "OllamaClient", lambda: mock_client)

    response = client.post("/api/ollama/test", json={"prompt": "ping"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["reply"] == "ok"
    assert "latency_ms" in body


def test_templates_crud(studio_client):
    client, _, _, _ = studio_client

    created = client.post(
        "/api/templates",
        json={"name": "Ack", "body": "Hi {sender_first_name},"},
    )
    assert created.status_code == 200
    template_id = created.json()["id"]

    listed = client.get("/api/templates")
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1

    patched = client.patch(
        f"/api/templates/{template_id}",
        json={"body": "Hello {sender_first_name},"},
    )
    assert patched.status_code == 200
    assert patched.json()["body"].startswith("Hello")

    deleted = client.delete(f"/api/templates/{template_id}")
    assert deleted.status_code == 200
    assert client.get("/api/templates").json()["items"] == []


def test_template_ai_assist_mocked(studio_client, monkeypatch: pytest.MonkeyPatch):
    client, _, _, _ = studio_client
    mock_client = MagicMock()
    mock_client.chat_text.return_value = (
        "Hi {sender_first_name},\n{ai_response}\nBest, {team_name}\n"
        "AI instructions: Keep it brief."
    )
    monkeypatch.setattr(web_app, "OllamaClient", lambda: mock_client)

    response = client.post(
        "/api/templates/ai-assist",
        json={"description": "Short acknowledgement"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "{sender_first_name}" in body["body"]
    assert body["ai_instructions"] == "Keep it brief."


def test_rules_crud(studio_client):
    client, _, _, _ = studio_client

    tpl = client.post("/api/templates", json={"name": "T1", "body": "Hi"})
    template_id = tpl.json()["id"]

    created = client.post(
        "/api/rules",
        json={
            "name": "Test rule",
            "template_id": template_id,
            "match": {"subject_keywords": ["invoice"], "mode": "any"},
        },
    )
    assert created.status_code == 200
    rule_id = created.json()["id"]

    listed = client.get("/api/rules")
    assert len(listed.json()["items"]) == 1

    patched = client.patch(f"/api/rules/{rule_id}", json={"enabled": False})
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False

    deleted = client.delete(f"/api/rules/{rule_id}")
    assert deleted.status_code == 200


def test_poller_get_put(studio_client):
    client, store, _, _ = studio_client

    response = client.get("/api/email-settings/poller")
    assert response.status_code == 200
    assert response.json()["enabled"] is False

    updated = client.put(
        "/api/email-settings/poller",
        json={"enabled": True, "interval_seconds": 120},
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is True
    assert updated.json()["interval_seconds"] == 120

    reloaded = store.load_poller_state()
    assert reloaded.enabled is True
    assert reloaded.interval_seconds == 120


def test_process_now_job(studio_client, monkeypatch: pytest.MonkeyPatch):
    client, store, _, _ = studio_client

    mock_result = MagicMock()
    mock_result.processed = 2
    mock_result.last_message_id = "msg-newest"
    mock_result.as_dict.return_value = {
        "processed": 2,
        "last_message_id": "msg-newest",
        "errors": [],
    }
    monkeypatch.setattr(
        "app.inbox_processor.process_inbox",
        lambda **kwargs: mock_result,
    )

    response = client.post("/api/email-settings/process-now", json={"top": 10})
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    job = {"status": "pending"}
    for _ in range(50):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)

    assert job["status"] == "completed"
    assert job["result"]["processed"] == 2

    state = store.load_poller_state()
    assert state.last_processed_message_id == "msg-newest"
    assert state.last_processed_count == 2


def test_queue_approval_approve_reject(studio_client):
    client, store, _, _ = studio_client
    entry = QueueEntry(
        id="q_api_test",
        created_at=store.utc_now(),
        message_id="msg-1",
        rule_id="rule_1",
        template_id="tpl_1",
        subject="Re: hello",
        body="Thanks",
        status="pending",
    )
    store.append_entry("approval", entry)

    pending = client.get("/api/queue/approval")
    assert pending.status_code == 200
    assert len(pending.json()["items"]) == 1

    approved = client.post("/api/queue/approval/q_api_test/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    entry2 = QueueEntry(
        id="q_api_reject",
        created_at=store.utc_now(),
        message_id="msg-2",
        rule_id="rule_1",
        template_id="tpl_1",
        subject="Re: hi",
        body="No thanks",
        status="pending",
    )
    store.append_entry("approval", entry2)
    rejected = client.post("/api/queue/approval/q_api_reject/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"


def test_queue_auto_read_only(studio_client):
    client, store, _, _ = studio_client
    entry = QueueEntry(
        id="q_auto_1",
        created_at=store.utc_now(),
        message_id="msg-auto",
        rule_id="rule_1",
        template_id="tpl_1",
        subject="Re: auto",
        body="Auto reply",
        status="pending",
    )
    store.append_entry("auto", entry)

    response = client.get("/api/queue/auto")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


def test_poller_start_stop_and_state(tmp_path: Path):
    store = ResponseQueueStore(tmp_path / "queue")
    poller = BackgroundPoller(queue_store=store, interval_seconds=1)
    poller.save_state(PollerState(enabled=False))

    async def _exercise() -> None:
        await poller.start()
        await asyncio.sleep(0.05)
        await poller.stop()

    asyncio.run(_exercise())

    state = store.load_poller_state()
    assert state.enabled is False


def test_poller_run_once_updates_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = ResponseQueueStore(tmp_path / "queue")
    poller = BackgroundPoller(queue_store=store)
    poller.save_state(PollerState(enabled=True, last_processed_message_id="old-cursor"))

    mock_result = MagicMock()
    mock_result.processed = 3
    mock_result.last_message_id = "cursor-new"
    mock_result.as_dict.return_value = {
        "processed": 3,
        "last_message_id": "cursor-new",
        "errors": [],
        "emails": [],
    }
    monkeypatch.setattr("app.web.poller.process_inbox", lambda **kwargs: mock_result)

    payload = poller.run_once()
    assert payload["processed"] == 3

    state = store.load_poller_state()
    assert state.last_processed_message_id == "cursor-new"
    assert state.last_processed_count == 3
    assert state.last_run is not None
