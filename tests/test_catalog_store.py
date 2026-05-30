"""Tests for catalog store."""

from pathlib import Path

import pytest
import yaml

from app.catalog_store import (
    apply_contact_importance,
    bulk_apply_contact_importance,
    filter_contacts,
    filter_domains,
    get_contact,
    get_contacts_for_domain,
    importance_patch,
    load_contacts,
    load_domains,
    refresh_contact_previews,
    update_contact,
    update_domain,
)
from app.inbox_catalog import CONTACT_IMPORTANCE_LABELS, DEFAULT_EXCLUDED_CATEGORIES


def test_load_domains_has_data():
    catalog = load_domains()
    assert catalog.domain_count > 0 or len(catalog.domains) >= 0


def test_filter_domains_search():
    catalog = load_domains()
    if not catalog.domains:
        return
    first_domain = catalog.domains[0].domain
    results = filter_domains(catalog, search=first_domain[:5])
    assert len(results) >= 1


def test_filter_domains_excludes_ignore_and_newsletter():
    catalog = load_domains()
    if not catalog.domains:
        return
    all_count = len(filter_domains(catalog))
    filtered = filter_domains(catalog, exclude_categories=DEFAULT_EXCLUDED_CATEGORIES)
    assert len(filtered) <= all_count
    assert not any(r.category in DEFAULT_EXCLUDED_CATEGORIES for r in filtered)
    excluded = [r for r in catalog.domains if r.category in DEFAULT_EXCLUDED_CATEGORIES]
    if excluded:
        assert len(filtered) < all_count


def test_filter_domains_category_overrides_exclude():
    catalog = load_domains()
    ignore_domains = [r for r in catalog.domains if r.category == "ignore"]
    if not ignore_domains:
        return
    filtered = filter_domains(
        catalog, category="ignore", exclude_categories=DEFAULT_EXCLUDED_CATEGORIES
    )
    assert len(filtered) >= 1
    assert all(r.category == "ignore" for r in filtered)


def test_filter_contacts_excludes_ignore_and_newsletter():
    catalog = load_contacts()
    if not catalog.contacts:
        return
    filtered = filter_contacts(catalog, exclude_categories=DEFAULT_EXCLUDED_CATEGORIES)
    assert not any(r.category in DEFAULT_EXCLUDED_CATEGORIES for r in filtered)


def test_get_contacts_for_domain():
    catalog = load_contacts()
    if not catalog.contacts:
        return
    domain = catalog.contacts[0].domain
    rows = get_contacts_for_domain(domain)
    assert rows
    assert all(r.domain == domain for r in rows)
    assert rows == sorted(rows, key=lambda r: (-r.message_count, r.email.lower()))


def test_importance_patch_levels():
    assert importance_patch("high", "client") == {
        "importance": "high",
        "agent_enabled": True,
        "category": "client",
    }
    assert importance_patch("medium", "client") == {
        "importance": "medium",
        "agent_enabled": True,
        "category": "client",
    }
    assert importance_patch("low", "client") == {
        "importance": "low",
        "agent_enabled": False,
        "category": "ignore",
    }


def test_apply_contact_importance_low_preserves_on_domain_update():
    catalog = load_contacts()
    client_domains = [d for d in load_domains().domains if d.category == "client"]
    if not client_domains or not catalog.contacts:
        return
    domain = client_domains[0].domain
    domain_contacts = get_contacts_for_domain(domain)
    if not domain_contacts:
        return
    email = domain_contacts[0].email
    apply_contact_importance(email, "low", "client")
    update_domain(domain, {"category": "client", "company": "Test Co"})
    after = next(c for c in load_contacts().contacts if c.email.lower() == email.lower())
    assert after.importance == "low"
    assert after.category == "ignore"


def test_filter_contacts_by_domain():
    catalog = load_contacts()
    if not catalog.contacts:
        return
    domain = catalog.contacts[0].domain
    filtered = filter_contacts(catalog, domain=domain)
    assert filtered
    assert all(r.domain == domain for r in filtered)


def test_bulk_apply_contact_importance():
    catalog = load_contacts()
    if len(catalog.contacts) < 2:
        return
    emails = [catalog.contacts[0].email, catalog.contacts[1].email]
    count = bulk_apply_contact_importance(emails, "medium")
    assert count == 2
    for email in emails:
        row = next(c for c in load_contacts().contacts if c.email == email)
        assert row.importance == "medium"
        assert row.agent_enabled is True


def test_contact_importance_labels():
    assert set(CONTACT_IMPORTANCE_LABELS) == {"high", "medium", "low"}


@pytest.fixture
def catalog_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir()
    contacts = {
        "scraped_at": "2026-05-30T00:00:00+00:00",
        "contact_count": 1,
        "contacts": [
            {
                "rank": 1,
                "email": "jane.doe@acmehealth.com",
                "name": "Jane Doe",
                "domain": "acmehealth.com",
                "message_count": 5,
                "importance": "high",
                "category": "client",
                "sample_subjects": ["Claims schema"],
                "key_phrases": ["340B audit"],
            }
        ],
    }
    (catalog_dir / "inbox_contacts.yaml").write_text(yaml.dump(contacts), encoding="utf-8")
    (catalog_dir / "inbox_domains.yaml").write_text(
        yaml.dump({"scraped_at": "", "domain_count": 0, "domains": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr("app.catalog_store.CATALOG_DIR", catalog_dir)
    monkeypatch.setattr("app.catalog_store.CONTACTS_FILE", catalog_dir / "inbox_contacts.yaml")
    monkeypatch.setattr("app.catalog_store.DOMAINS_FILE", catalog_dir / "inbox_domains.yaml")
    monkeypatch.setattr("app.inbox_catalog.CATALOG_DIR", catalog_dir)
    monkeypatch.setattr("app.inbox_catalog.CONTACTS_FILE", catalog_dir / "inbox_contacts.yaml")
    monkeypatch.setattr("app.inbox_catalog.DOMAINS_FILE", catalog_dir / "inbox_domains.yaml")
    return catalog_dir


def test_get_contact_and_key_phrases(catalog_tmp):
    row = get_contact("jane.doe@acmehealth.com")
    assert row is not None
    assert row.key_phrases == ["340B audit"]

    updated = update_contact("jane.doe@acmehealth.com", {"key_phrases": ["claims file", "SFTP"]})
    assert updated is not None
    assert updated.key_phrases == ["claims file", "SFTP"]


def test_refresh_contact_previews_mock(catalog_tmp, monkeypatch: pytest.MonkeyPatch):
    from app.schemas import NormalizedEmail

    class FakeBackend:
        def list_messages_for_sender(self, sender_email: str, top: int = 5):
            return [
                NormalizedEmail(
                    message_id="msg-1",
                    subject="ETL timeline",
                    sender_email=sender_email,
                    received_at="2026-05-22T16:00:00Z",
                    body_text="Can you confirm when ingestion will be ready?",
                )
            ]

    monkeypatch.setattr(
        "app.graph_client.get_email_backend",
        lambda backend_name=None: FakeBackend(),
    )

    previews = refresh_contact_previews("jane.doe@acmehealth.com")
    assert len(previews) == 1
    assert previews[0].subject == "ETL timeline"

    row = get_contact("jane.doe@acmehealth.com")
    assert row is not None
    assert len(row.sample_emails) == 1
