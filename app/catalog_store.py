"""Read/write inbox catalog YAML for API and UI."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from app.inbox_catalog import (
    CATALOG_DIR,
    CONTACT_IMPORTANCE_LABELS,
    CONTACTS_FILE,
    DOMAINS_FILE,
)


class SampleEmailRow(BaseModel):
    message_id: str = ""
    subject: str = ""
    sender_email: str = ""
    sender_name: str | None = None
    received_at: str = ""
    body_preview: str = ""


class DomainRow(BaseModel):
    domain: str
    message_count: int = 0
    contact_count: int = 0
    first_seen: str = ""
    last_seen: str = ""
    suggested_category: str = "unassigned"
    category: str = "unassigned"
    company: str | None = None
    config_client_abbrev: str | None = None
    config_client_name: str | None = None
    sample_subjects: list[str] = Field(default_factory=list)
    sample_emails: list[SampleEmailRow] = Field(default_factory=list)
    contacts: list[str] = Field(default_factory=list)


class ContactRow(BaseModel):
    rank: int = 0
    email: str
    name: str | None = None
    domain: str = ""
    message_count: int = 0
    rank_score: float = 0.0
    importance: str = "medium"
    agent_enabled: bool = False
    category: str = "unassigned"
    company: str | None = None
    first_seen: str = ""
    last_seen: str = ""
    sample_subjects: list[str] = Field(default_factory=list)
    sample_emails: list[SampleEmailRow] = Field(default_factory=list)
    key_phrases: list[str] = Field(default_factory=list)


class DomainCatalog(BaseModel):
    scraped_at: str = ""
    domain_count: int = 0
    domains: list[DomainRow] = Field(default_factory=list)


class ContactCatalog(BaseModel):
    scraped_at: str = ""
    contact_count: int = 0
    contacts: list[ContactRow] = Field(default_factory=list)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_domains() -> DomainCatalog:
    raw = _load_yaml(DOMAINS_FILE)
    return DomainCatalog.model_validate(raw) if raw.get("domains") is not None else DomainCatalog()


def load_contacts() -> ContactCatalog:
    raw = _load_yaml(CONTACTS_FILE)
    return (
        ContactCatalog.model_validate(raw) if raw.get("contacts") is not None else ContactCatalog()
    )


def save_domains(catalog: DomainCatalog) -> None:
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    catalog.domain_count = len(catalog.domains)
    if not catalog.scraped_at:
        catalog.scraped_at = datetime.now(UTC).isoformat()
    DOMAINS_FILE.write_text(
        yaml.dump(catalog.model_dump(), default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def save_contacts(catalog: ContactCatalog) -> None:
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    catalog.contact_count = len(catalog.contacts)
    if not catalog.scraped_at:
        catalog.scraped_at = datetime.now(UTC).isoformat()
    CONTACTS_FILE.write_text(
        yaml.dump(catalog.model_dump(), default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def get_domain(domain: str) -> DomainRow | None:
    catalog = load_domains()
    for row in catalog.domains:
        if row.domain == domain:
            return row
    return None


def get_contact(email: str) -> ContactRow | None:
    catalog = load_contacts()
    key = email.lower()
    for row in catalog.contacts:
        if row.email.lower() == key:
            return row
    return None


def refresh_contact_previews(email: str, limit: int = 5) -> list[SampleEmailRow]:
    """Fetch live email previews from Graph for a sender and save to catalog."""
    from app.graph_client import get_email_backend

    backend = get_email_backend()
    if not hasattr(backend, "list_messages_for_sender"):
        raise RuntimeError("Backend does not support list_messages_for_sender")
    messages = backend.list_messages_for_sender(email, top=limit)
    previews = [
        SampleEmailRow(
            message_id=m.message_id,
            subject=m.subject,
            sender_email=m.sender_email,
            sender_name=m.sender_name,
            received_at=m.received_at,
            body_preview=(m.body_text or "")[:500],
        )
        for m in messages
    ]
    catalog = load_contacts()
    key = email.lower()
    for row in catalog.contacts:
        if row.email.lower() == key:
            row.sample_emails = previews
            if previews and not row.sample_subjects:
                row.sample_subjects = [p.subject for p in previews[:5]]
            save_contacts(catalog)
            break
    return previews


def refresh_domain_previews(domain: str, limit: int = 5) -> list[SampleEmailRow]:
    """Fetch live email previews from Graph and save to catalog."""
    from app.graph_client import MsGraphBackend

    backend = MsGraphBackend()
    messages = backend.list_messages_for_domain(domain, top=limit)
    previews = [
        SampleEmailRow(
            message_id=m.message_id,
            subject=m.subject,
            sender_email=m.sender_email,
            sender_name=m.sender_name,
            received_at=m.received_at,
            body_preview=(m.body_text or "")[:500],
        )
        for m in messages
    ]
    catalog = load_domains()
    for row in catalog.domains:
        if row.domain == domain:
            row.sample_emails = previews
            if previews and not row.sample_subjects:
                row.sample_subjects = [p.subject for p in previews[:5]]
            save_domains(catalog)
            break
    return previews


def update_domain(domain: str, patch: dict[str, Any]) -> DomainRow | None:
    catalog = load_domains()
    for row in catalog.domains:
        if row.domain == domain:
            for k, v in patch.items():
                if hasattr(row, k):
                    setattr(row, k, v)
            save_domains(catalog)
            _sync_contact_domain_category(domain, row.category, row.company)
            return row
    return None


def bulk_update_domains(domains: list[str], patch: dict[str, Any]) -> int:
    catalog = load_domains()
    updated = 0
    for row in catalog.domains:
        if row.domain in domains:
            for k, v in patch.items():
                if hasattr(row, k):
                    setattr(row, k, v)
            _sync_contact_domain_category(row.domain, row.category, row.company)
            updated += 1
    if updated:
        save_domains(catalog)
    return updated


def update_contact(email: str, patch: dict[str, Any]) -> ContactRow | None:
    catalog = load_contacts()
    key = email.lower()
    for row in catalog.contacts:
        if row.email.lower() == key:
            for k, v in patch.items():
                if hasattr(row, k):
                    setattr(row, k, v)
            save_contacts(catalog)
            return row
    return None


def get_contacts_for_domain(domain: str) -> list[ContactRow]:
    """Contacts belonging to a domain, sorted by message volume."""
    domain_key = domain.lower()
    rows = [r for r in load_contacts().contacts if r.domain.lower() == domain_key]
    return sorted(rows, key=lambda r: (-r.message_count, r.email.lower()))


def apply_contact_importance(
    email: str, importance: str, domain_category: str
) -> ContactRow | None:
    catalog = load_contacts()
    key = email.lower()
    for row in catalog.contacts:
        if row.email.lower() == key:
            patch = importance_patch(importance, domain_category, row)
            for k, v in patch.items():
                setattr(row, k, v)
            save_contacts(catalog)
            return row
    return None


def bulk_apply_contact_importance(emails: list[str], importance: str) -> int:
    updated = 0
    for email in emails:
        catalog = load_contacts()
        contact = next((c for c in catalog.contacts if c.email.lower() == email.lower()), None)
        if not contact:
            continue
        domain_row = get_domain(contact.domain)
        domain_category = domain_row.category if domain_row else contact.category
        if apply_contact_importance(email, importance, domain_category):
            updated += 1
    return updated


def importance_patch(
    importance: str,
    domain_category: str,
    contact: ContactRow | None = None,
) -> dict[str, Any]:
    """Map importance level to contact field updates."""
    if importance not in CONTACT_IMPORTANCE_LABELS:
        raise ValueError(f"Unknown importance: {importance}")

    inherit_cat = domain_category
    if inherit_cat in ("ignore", "newsletter") and contact:
        inherit_cat = (
            contact.category if contact.category not in ("ignore", "newsletter") else "unassigned"
        )

    if importance == "low":
        return {"importance": "low", "agent_enabled": False, "category": "ignore"}
    if importance == "high":
        return {"importance": "high", "agent_enabled": True, "category": inherit_cat}
    return {"importance": "medium", "agent_enabled": True, "category": inherit_cat}


def _sync_contact_domain_category(domain: str, category: str, company: str | None) -> None:
    catalog = load_contacts()
    changed = False
    for row in catalog.contacts:
        if row.domain != domain:
            continue
        # Preserve per-contact low/ignore within an actionable domain
        if row.importance == "low" or (
            row.category == "ignore" and category not in ("ignore", "newsletter")
        ):
            row.agent_enabled = False
            if row.importance != "low":
                row.importance = "low"
            changed = True
            continue
        row.category = category
        if company:
            row.company = company
        if category in ("ignore", "newsletter", "personal"):
            row.agent_enabled = False
        changed = True
    if changed:
        save_contacts(catalog)


def filter_domains(
    catalog: DomainCatalog,
    search: str = "",
    category: str = "",
    sort: str = "message_count",
    desc: bool = True,
    exclude_categories: frozenset[str] | None = None,
) -> list[DomainRow]:
    rows = catalog.domains
    if search:
        q = search.lower()
        rows = [
            r
            for r in rows
            if q in r.domain.lower()
            or (r.company and q in r.company.lower())
            or (r.config_client_abbrev and q in r.config_client_abbrev.lower())
            or (r.config_client_name and q in r.config_client_name.lower())
            or any(q in s.lower() for s in r.sample_subjects)
            or any(
                q in (e.subject or "").lower() or q in (e.body_preview or "").lower()
                for e in r.sample_emails
            )
        ]
    if category:
        rows = [r for r in rows if r.category == category]
    elif exclude_categories:
        rows = [r for r in rows if r.category not in exclude_categories]
    reverse = desc
    if sort == "domain":
        rows = sorted(rows, key=lambda r: r.domain.lower(), reverse=reverse)
    elif sort == "company":
        rows = sorted(rows, key=lambda r: (r.company or "").lower(), reverse=reverse)
    else:
        rows = sorted(rows, key=lambda r: r.message_count, reverse=reverse)
    return rows


def filter_contacts(
    catalog: ContactCatalog,
    search: str = "",
    domain: str = "",
    category: str = "",
    importance: str = "",
    agent_only: bool = False,
    exclude_categories: frozenset[str] | None = None,
) -> list[ContactRow]:
    rows = catalog.contacts
    if domain:
        domain_key = domain.lower()
        rows = [r for r in rows if r.domain.lower() == domain_key]
    if search:
        q = search.lower()
        rows = [
            r
            for r in rows
            if q in r.email.lower()
            or (r.name and q in r.name.lower())
            or (r.company and q in r.company.lower())
            or any(q in s.lower() for s in r.sample_subjects)
            or any(
                q in (e.subject or "").lower() or q in (e.body_preview or "").lower()
                for e in r.sample_emails
            )
            or any(q in phrase.lower() for phrase in r.key_phrases)
        ]
    if category:
        rows = [r for r in rows if r.category == category]
    elif exclude_categories:
        rows = [r for r in rows if r.category not in exclude_categories]
    if importance:
        rows = [r for r in rows if r.importance == importance]
    if agent_only:
        rows = [r for r in rows if r.agent_enabled]
    return rows
