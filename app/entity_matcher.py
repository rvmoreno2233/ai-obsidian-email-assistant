"""Rule-based entity matching against YAML catalogs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.config import DATA_DIR
from app.schemas import (
    CompaniesCatalog,
    ContactsCatalog,
    EntityMatchResult,
    NormalizedEmail,
    ProjectsCatalog,
    WaitingForCatalog,
    WaitingItem,
    WaitingItemMatch,
)


@dataclass
class Catalogs:
    companies: CompaniesCatalog
    contacts: ContactsCatalog
    projects: ProjectsCatalog
    waiting_for: WaitingForCatalog


def _load_yaml(path: Path, model_class: type):
    if not path.exists():
        return model_class()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return model_class.model_validate(data)


def load_catalogs(data_dir: Path | None = None) -> Catalogs:
    base = data_dir or DATA_DIR
    return Catalogs(
        companies=_load_yaml(base / "companies.yaml", CompaniesCatalog),
        contacts=_load_yaml(base / "contacts.yaml", ContactsCatalog),
        projects=_load_yaml(base / "projects.yaml", ProjectsCatalog),
        waiting_for=_load_yaml(base / "waiting_for.yaml", WaitingForCatalog),
    )


def _sender_domain(email: str) -> str:
    if "@" not in email:
        return ""
    return email.split("@", 1)[1].lower()


def _text_blob(email: NormalizedEmail) -> str:
    parts = [email.subject, email.body_text, email.sender_email]
    if email.sender_name:
        parts.append(email.sender_name)
    return " ".join(parts).lower()


def match_company(email: NormalizedEmail, catalogs: Catalogs) -> str | None:
    domain = _sender_domain(email.sender_email)
    blob = _text_blob(email)

    # Domain match wins — never override with body keywords
    for company in catalogs.companies.companies:
        if domain and any(d.lower() in domain or domain.endswith(d.lower()) for d in company.domains):
            return company.name
        if email.sender_email.lower() in {c.lower() for c in company.contacts}:
            return company.name

    best: tuple[int, str] | None = None
    for company in catalogs.companies.companies:
        for kw in company.keywords:
            if kw.lower() in blob:
                score = len(kw)
                if best is None or score > best[0]:
                    best = (score, company.name)

    return best[1] if best else None


def match_contact(email: NormalizedEmail, catalogs: Catalogs) -> str | None:
    sender = email.sender_email.lower()
    for contact in catalogs.contacts.contacts:
        if contact.email.lower() == sender:
            return contact.name
    return email.sender_name


def match_projects(
    email: NormalizedEmail,
    catalogs: Catalogs,
    company: str | None,
) -> list[str]:
    blob = _text_blob(email)
    matched: list[tuple[int, str]] = []

    for project in catalogs.projects.projects:
        if company and project.company and project.company != company:
            continue
        for kw in project.keywords:
            if kw.lower() in blob:
                matched.append((len(kw), project.name))
                break

    matched.sort(key=lambda x: -x[0])
    seen: set[str] = set()
    result: list[str] = []
    for _, name in matched:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def match_waiting_items(
    email: NormalizedEmail,
    catalogs: Catalogs,
) -> list[WaitingItemMatch]:
    blob = _text_blob(email)
    results: list[WaitingItemMatch] = []

    for item in catalogs.waiting_for.waiting_for:
        if item.status != "open":
            continue
        evidence_parts: list[str] = []
        for kw in item.keywords:
            if kw.lower() in blob:
                evidence_parts.append(kw)
        # Require substantive match: multi-word phrase or multiple keywords
        strong = [e for e in evidence_parts if " " in e or len(e) >= 12]
        matched = len(strong) >= 1 or len(evidence_parts) >= 2
        confidence = min(1.0, 0.5 + 0.15 * len(evidence_parts)) if matched else 0.0
        results.append(
            WaitingItemMatch(
                waiting_item_id=item.id,
                project=item.project,
                matched=matched,
                evidence=", ".join(evidence_parts) if evidence_parts else "",
                confidence=confidence,
            )
        )
    return results


def match_entities(
    email: NormalizedEmail,
    catalogs: Catalogs | None = None,
) -> EntityMatchResult:
    """Match email to company, contact, projects, and waiting-for items."""
    cat = catalogs or load_catalogs()
    company = match_company(email, cat)
    contact = match_contact(email, cat)
    projects = match_projects(email, cat, company)
    waiting = match_waiting_items(email, cat)
    tags: list[str] = []
    if company:
        tags.append(f"company:{company}")
    for p in projects:
        tags.append(f"project:{p}")

    return EntityMatchResult(
        company=company,
        contact=contact,
        projects=projects,
        tags=tags,
        waiting_matches=waiting,
    )


def get_open_waiting_items(catalogs: Catalogs) -> list[WaitingItem]:
    return [w for w in catalogs.waiting_for.waiting_for if w.status == "open"]


def is_newsletter_sender(email: NormalizedEmail) -> bool:
    from app.config import NEWSLETTER_DOMAINS

    domain = _sender_domain(email.sender_email)
    local = email.sender_email.split("@", 1)[0].lower()
    if any(nd in domain for nd in NEWSLETTER_DOMAINS):
        return True
    if local in ("noreply", "no-reply", "donotreply"):
        return True
    blob = _text_blob(email)
    if "unsubscribe" in blob or "list-unsubscribe" in blob:
        return True
    if re.search(r"\b(sale|discount|promo|webinar)\b", blob):
        return True
    return False
