"""Tests for email knowledge base sync, search, and recontextualize."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from app.email_knowledge import (
    EmailContext,
    is_sender_approved,
    knowledge_stats,
    load_entries,
    recontextualize_entries,
    search_knowledge,
    sync_knowledge_from_fixture,
)
from app.schemas import NormalizedEmail


@pytest.fixture
def knowledge_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir()
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()

    domains = {
        "scraped_at": "2026-05-30T00:00:00+00:00",
        "domain_count": 2,
        "domains": [
            {
                "domain": "acmehealth.com",
                "message_count": 10,
                "category": "client",
                "company": "Acme Health",
            },
            {
                "domain": "mailchimp.com",
                "message_count": 5,
                "category": "newsletter",
            },
        ],
    }
    contacts = {
        "scraped_at": "2026-05-30T00:00:00+00:00",
        "contact_count": 2,
        "contacts": [
            {
                "email": "jane.doe@acmehealth.com",
                "domain": "acmehealth.com",
                "importance": "high",
                "category": "client",
                "company": "Acme Health",
            },
            {
                "email": "deals@mailchimp.com",
                "domain": "mailchimp.com",
                "importance": "medium",
                "category": "newsletter",
            },
        ],
    }
    (catalog_dir / "inbox_domains.yaml").write_text(yaml.dump(domains), encoding="utf-8")
    (catalog_dir / "inbox_contacts.yaml").write_text(yaml.dump(contacts), encoding="utf-8")

    monkeypatch.setattr("app.catalog_store.DOMAINS_FILE", catalog_dir / "inbox_domains.yaml")
    monkeypatch.setattr("app.catalog_store.CONTACTS_FILE", catalog_dir / "inbox_contacts.yaml")
    monkeypatch.setattr("app.catalog_store.CATALOG_DIR", catalog_dir)
    monkeypatch.setattr("app.inbox_catalog.CATALOG_DIR", catalog_dir)
    monkeypatch.setattr("app.inbox_catalog.DOMAINS_FILE", catalog_dir / "inbox_domains.yaml")
    monkeypatch.setattr("app.inbox_catalog.CONTACTS_FILE", catalog_dir / "inbox_contacts.yaml")

    monkeypatch.setattr("app.email_knowledge.KNOWLEDGE_DIR", knowledge_dir)
    monkeypatch.setattr("app.email_knowledge.INDEX_FILE", knowledge_dir / "emails.jsonl")
    monkeypatch.setattr("app.email_knowledge.MANIFEST_FILE", knowledge_dir / "manifest.yaml")

    yield knowledge_dir


def test_is_sender_approved(knowledge_env):
    ok, meta = is_sender_approved("jane.doe@acmehealth.com")
    assert ok is True
    assert meta["domain_category"] == "client"

    ok, _ = is_sender_approved("deals@mailchimp.com")
    assert ok is False

    ok, _ = is_sender_approved("unknown@vendor.com")
    assert ok is False


def test_sync_and_search(knowledge_env):
    emails = [
        NormalizedEmail(
            message_id="msg-1",
            subject="Claims schema approved",
            sender_email="jane.doe@acmehealth.com",
            sender_name="Jane Doe",
            received_at="2026-05-24T09:00:00Z",
            body_text="The claims schema has final approval from governance.",
        ),
        NormalizedEmail(
            message_id="msg-2",
            subject="50% off sale",
            sender_email="deals@mailchimp.com",
            received_at="2026-05-24T08:00:00Z",
            body_text="Biggest sale of the year.",
        ),
    ]
    result = sync_knowledge_from_fixture(
        emails, recontextualize_new=False, knowledge_dir=knowledge_env
    )
    assert result.added == 1
    assert result.skipped_unapproved == 1

    entries = load_entries()
    assert len(entries) == 1
    assert entries["msg-1"].subject == "Claims schema approved"

    hits = search_knowledge("claims schema", knowledge_dir=knowledge_env)
    assert len(hits) == 1
    assert hits[0].entry.message_id == "msg-1"


def test_recontextualize_fallback_without_llm(knowledge_env):
    emails = [
        NormalizedEmail(
            message_id="msg-ctx",
            subject="ETL timeline question",
            sender_email="jane.doe@acmehealth.com",
            received_at="2026-05-22T16:00:00Z",
            body_text="Can you confirm when ingestion will be ready?",
        ),
    ]
    sync_knowledge_from_fixture(emails, recontextualize_new=False, knowledge_dir=knowledge_env)

    mock_llm = MagicMock()
    from app.llm_client import LLMConnectionError

    mock_llm.chat_structured.side_effect = LLMConnectionError("offline")

    result = recontextualize_entries(knowledge_dir=knowledge_env, llm=mock_llm)
    assert result["updated"] == 1

    entry = load_entries()["msg-ctx"]
    assert entry.context is not None
    assert "ETL timeline" in entry.context.summary


def test_recontextualize_with_llm(knowledge_env):
    emails = [
        NormalizedEmail(
            message_id="msg-llm",
            subject="340B audit prep",
            sender_email="jane.doe@acmehealth.com",
            received_at="2026-05-21T09:00:00Z",
            body_text="Please send the latest 340B accumulator report.",
        ),
    ]
    sync_knowledge_from_fixture(emails, recontextualize_new=False, knowledge_dir=knowledge_env)

    mock_llm = MagicMock()
    mock_llm.chat_structured.return_value = EmailContext(
        summary="Request for 340B accumulator report ahead of audit.",
        topics=["340B", "audit"],
        action_items=["Send accumulator report"],
        entities=["Acme Health"],
    )

    result = recontextualize_entries(
        message_ids=["msg-llm"], knowledge_dir=knowledge_env, llm=mock_llm
    )
    assert result["updated"] == 1

    hits = search_knowledge("accumulator audit", knowledge_dir=knowledge_env)
    assert hits[0].entry.context.summary.startswith("Request for 340B")


def test_knowledge_stats(knowledge_env):
    emails = [
        NormalizedEmail(
            message_id="msg-stat",
            subject="Status update",
            sender_email="jane.doe@acmehealth.com",
            received_at="2026-05-20T12:00:00Z",
            body_text="Pipeline is green.",
        ),
    ]
    sync_knowledge_from_fixture(emails, recontextualize_new=False, knowledge_dir=knowledge_env)
    stats = knowledge_stats(knowledge_dir=knowledge_env)
    assert stats["entry_count"] == 1
    assert stats["approved_domain_count"] == 1
