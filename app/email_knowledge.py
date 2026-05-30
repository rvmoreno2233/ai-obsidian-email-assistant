"""Local email knowledge base — sync approved mail, recontextualize, and search."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import yaml
from pydantic import BaseModel, Field

from app.catalog_store import ContactRow, DomainRow, load_contacts, load_domains
from app.config import DATA_DIR, PROMPTS_DIR
from app.inbox_catalog import DEFAULT_EXCLUDED_CATEGORIES, MessageMeta
from app.schemas import NormalizedEmail

KNOWLEDGE_DIR = DATA_DIR / "knowledge"
INDEX_FILE = KNOWLEDGE_DIR / "emails.jsonl"
MANIFEST_FILE = KNOWLEDGE_DIR / "manifest.yaml"
MAX_BODY_CHARS = 8000


class EmailContext(BaseModel):
    summary: str = ""
    topics: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)


class KnowledgeEntry(BaseModel):
    message_id: str
    subject: str
    sender_email: str
    sender_name: str | None = None
    domain: str = ""
    received_at: str = ""
    body_text: str = ""
    body_preview: str = ""
    domain_category: str = ""
    company: str | None = None
    contact_importance: str = ""
    context: EmailContext | None = None
    indexed_at: str = ""
    context_at: str | None = None
    web_link: str | None = None


class KnowledgeManifest(BaseModel):
    last_sync_at: str | None = None
    entry_count: int = 0
    approved_domain_count: int = 0
    approved_contact_count: int = 0
    last_sync_added: int = 0
    last_sync_skipped: int = 0


class SyncResult(BaseModel):
    scanned: int = 0
    added: int = 0
    skipped_existing: int = 0
    skipped_unapproved: int = 0
    recontextualized: int = 0
    errors: list[str] = Field(default_factory=list)


class SearchHit(BaseModel):
    score: float
    entry: KnowledgeEntry
    snippet: str = ""


@runtime_checkable
class KnowledgeBackend(Protocol):
    """Fetch inbox metadata and full message bodies for knowledge sync."""

    def list_messages_metadata(
        self,
        folder: str = "inbox",
        page_size: int = 100,
        max_pages: int = 50,
    ) -> list[MessageMeta]: ...

    def get_message_preview(self, message_id: str) -> dict[str, Any]: ...


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sender_domain(sender_email: str) -> str:
    if "@" not in sender_email:
        return ""
    return sender_email.split("@", 1)[1].lower()


def _truncate(text: str, limit: int = MAX_BODY_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def load_manifest() -> KnowledgeManifest:
    if not MANIFEST_FILE.exists():
        return KnowledgeManifest()
    raw = yaml.safe_load(MANIFEST_FILE.read_text(encoding="utf-8")) or {}
    return KnowledgeManifest.model_validate(raw)


def save_manifest(manifest: KnowledgeManifest) -> None:
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_FILE.write_text(
        yaml.dump(manifest.model_dump(), default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def load_entries() -> dict[str, KnowledgeEntry]:
    if not INDEX_FILE.exists():
        return {}
    entries: dict[str, KnowledgeEntry] = {}
    for line in INDEX_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = KnowledgeEntry.model_validate(json.loads(line))
        entries[row.message_id] = row
    return entries


def save_entries(entries: dict[str, KnowledgeEntry]) -> None:
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    sorted_entries = sorted(entries.values(), key=lambda x: x.received_at, reverse=True)
    lines = [e.model_dump_json() for e in sorted_entries]
    INDEX_FILE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    manifest = load_manifest()
    manifest.entry_count = len(entries)
    save_manifest(manifest)


def get_entry(message_id: str) -> KnowledgeEntry | None:
    return load_entries().get(message_id)


def approval_stats() -> dict[str, int]:
    domains, contacts = _build_approval_index()
    approved_domains = sum(
        1 for d in domains.values() if d.category not in DEFAULT_EXCLUDED_CATEGORIES
    )
    approved_contacts = 0
    for c in contacts.values():
        domain_row = domains.get(c.domain.lower())
        domain_category = domain_row.category if domain_row else c.category
        if domain_category in DEFAULT_EXCLUDED_CATEGORIES:
            continue
        if c.importance in ("high", "medium"):
            approved_contacts += 1
    return {
        "approved_domain_count": approved_domains,
        "approved_contact_count": approved_contacts,
        "total_domains": len(domains),
        "total_contacts": len(contacts),
    }


def _build_approval_index() -> tuple[dict[str, DomainRow], dict[str, ContactRow]]:
    domains = {d.domain.lower(): d for d in load_domains().domains}
    contacts = {c.email.lower(): c for c in load_contacts().contacts}
    return domains, contacts


def is_sender_approved(
    sender_email: str,
    domains: dict[str, DomainRow] | None = None,
    contacts: dict[str, ContactRow] | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Return whether sender is in approved domains/contacts and metadata for indexing."""
    if domains is None or contacts is None:
        domains, contacts = _build_approval_index()

    email = sender_email.lower().strip()
    domain = _sender_domain(email)
    contact = contacts.get(email)
    domain_row = domains.get(domain)

    if contact and contact.importance == "low":
        return False, {}

    if contact:
        fallback_category = contact.category
    else:
        fallback_category = "unassigned"
    domain_category = domain_row.category if domain_row else fallback_category
    if domain_category in DEFAULT_EXCLUDED_CATEGORIES:
        return False, {}

    if contact and contact.importance in ("high", "medium"):
        return True, {
            "domain_category": domain_category,
            "company": contact.company or (domain_row.company if domain_row else None),
            "contact_importance": contact.importance,
        }

    if domain_row and domain_row.category not in DEFAULT_EXCLUDED_CATEGORIES:
        importance = contact.importance if contact else "medium"
        company = domain_row.company or domain_row.config_client_name
        return True, {
            "domain_category": domain_row.category,
            "company": company,
            "contact_importance": importance,
        }

    return False, {}


def _entry_from_preview(preview: dict[str, Any], meta: dict[str, Any]) -> KnowledgeEntry:
    sender_email = preview.get("sender_email") or ""
    body = _truncate(preview.get("body_text") or preview.get("body_preview") or "")
    return KnowledgeEntry(
        message_id=preview.get("message_id") or "",
        subject=preview.get("subject") or "",
        sender_email=sender_email,
        sender_name=preview.get("sender_name"),
        domain=_sender_domain(sender_email),
        received_at=preview.get("received_at") or "",
        body_text=body,
        body_preview=(preview.get("body_preview") or body)[:500],
        domain_category=meta.get("domain_category", ""),
        company=meta.get("company"),
        contact_importance=meta.get("contact_importance", ""),
        indexed_at=_utc_now(),
        web_link=preview.get("web_link"),
    )


def _entry_from_normalized(email: NormalizedEmail, meta: dict[str, Any]) -> KnowledgeEntry:
    body = _truncate(email.body_text or "")
    return KnowledgeEntry(
        message_id=email.message_id,
        subject=email.subject,
        sender_email=email.sender_email,
        sender_name=email.sender_name,
        domain=_sender_domain(email.sender_email),
        received_at=email.received_at,
        body_text=body,
        body_preview=body[:500],
        domain_category=meta.get("domain_category", ""),
        company=meta.get("company"),
        contact_importance=meta.get("contact_importance", ""),
        indexed_at=_utc_now(),
        web_link=email.web_link,
    )


def sync_knowledge(
    *,
    backend: KnowledgeBackend,
    max_pages: int = 50,
    page_size: int = 100,
    recontextualize_new: bool = True,
    knowledge_dir: Path | None = None,
) -> SyncResult:
    """Scan inbox metadata, copy approved emails into the local knowledge index."""
    global KNOWLEDGE_DIR, INDEX_FILE, MANIFEST_FILE
    if knowledge_dir:
        KNOWLEDGE_DIR = knowledge_dir
        INDEX_FILE = knowledge_dir / "emails.jsonl"
        MANIFEST_FILE = knowledge_dir / "manifest.yaml"

    result = SyncResult()
    domains, contacts = _build_approval_index()
    existing = load_entries()
    messages = backend.list_messages_metadata(page_size=page_size, max_pages=max_pages)
    result.scanned = len(messages)

    added_ids: list[str] = []
    for msg in messages:
        approved, meta = is_sender_approved(msg.sender_email, domains, contacts)
        if not approved:
            result.skipped_unapproved += 1
            continue
        if msg.message_id in existing:
            result.skipped_existing += 1
            continue
        try:
            preview = backend.get_message_preview(msg.message_id)
            if not preview:
                preview = {
                    "message_id": msg.message_id,
                    "subject": msg.subject,
                    "sender_email": msg.sender_email,
                    "sender_name": msg.sender_name,
                    "received_at": msg.received_at,
                    "body_preview": msg.body_preview,
                    "body_text": msg.body_preview,
                }
            entry = _entry_from_preview(preview, meta)
            existing[entry.message_id] = entry
            added_ids.append(entry.message_id)
            result.added += 1
        except Exception as exc:
            result.errors.append(f"{msg.message_id}: {exc}")

    save_entries(existing)

    if recontextualize_new and added_ids:
        rectx = recontextualize_entries(message_ids=added_ids, knowledge_dir=knowledge_dir)
        result.recontextualized = rectx.get("updated", 0)
        result.errors.extend(rectx.get("errors", []))

    stats = approval_stats()
    manifest = load_manifest()
    manifest.last_sync_at = _utc_now()
    manifest.last_sync_added = result.added
    manifest.last_sync_skipped = result.skipped_existing + result.skipped_unapproved
    manifest.approved_domain_count = stats["approved_domain_count"]
    manifest.approved_contact_count = stats["approved_contact_count"]
    manifest.entry_count = len(existing)
    save_manifest(manifest)
    return result


def sync_knowledge_from_fixture(
    emails: list[NormalizedEmail],
    *,
    recontextualize_new: bool = False,
    knowledge_dir: Path | None = None,
) -> SyncResult:
    """Sync from in-memory emails (mock/tests) without Graph."""

    class _FixtureBackend:
        def list_messages_metadata(
            self,
            folder: str = "inbox",
            page_size: int = 100,
            max_pages: int = 50,
        ):
            return [
                MessageMeta(
                    message_id=e.message_id,
                    subject=e.subject,
                    sender_email=e.sender_email,
                    sender_name=e.sender_name,
                    received_at=e.received_at,
                    body_preview=(e.body_text or "")[:500],
                )
                for e in emails
            ]

        def get_message_preview(self, message_id: str) -> dict[str, Any]:
            for e in emails:
                if e.message_id == message_id:
                    return {
                        "message_id": e.message_id,
                        "subject": e.subject,
                        "sender_email": e.sender_email,
                        "sender_name": e.sender_name,
                        "received_at": e.received_at,
                        "body_preview": (e.body_text or "")[:500],
                        "body_text": e.body_text,
                        "web_link": e.web_link,
                    }
            return {}

    return sync_knowledge(
        backend=_FixtureBackend(),
        max_pages=1,
        page_size=len(emails) or 100,
        recontextualize_new=recontextualize_new,
        knowledge_dir=knowledge_dir,
    )


def recontextualize_entries(
    *,
    message_ids: list[str] | None = None,
    force: bool = False,
    llm=None,
    knowledge_dir: Path | None = None,
) -> dict[str, Any]:
    """Generate or refresh LLM context summaries for indexed emails."""
    global KNOWLEDGE_DIR, INDEX_FILE, MANIFEST_FILE
    if knowledge_dir:
        KNOWLEDGE_DIR = knowledge_dir
        INDEX_FILE = knowledge_dir / "emails.jsonl"
        MANIFEST_FILE = knowledge_dir / "manifest.yaml"

    entries = load_entries()
    if message_ids:
        targets = [entries[mid] for mid in message_ids if mid in entries]
    else:
        targets = [e for e in entries.values() if force or not e.context_at]

    updated = 0
    errors: list[str] = []
    prompt_path = PROMPTS_DIR / "recontextualize_email.md"
    system_prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""

    if llm is None:
        from app.llm_client import OllamaClient

        llm = OllamaClient()

    for entry in targets:
        skip_existing = entry.context_at and not force and not message_ids
        if skip_existing:
            continue
        try:
            context = _generate_context(entry, llm, system_prompt)
            entry.context = context
            entry.context_at = _utc_now()
            entries[entry.message_id] = entry
            updated += 1
        except Exception as exc:
            errors.append(f"{entry.message_id}: {exc}")

    if updated:
        save_entries(entries)
    return {"updated": updated, "errors": errors}


def _generate_context(entry: KnowledgeEntry, llm, system_prompt: str) -> EmailContext:
    from app.llm_client import LLMConnectionError

    user_content = (
        f"Subject: {entry.subject}\n"
        f"From: {entry.sender_name or entry.sender_email} <{entry.sender_email}>\n"
        f"Date: {entry.received_at}\n"
        f"Domain category: {entry.domain_category}\n"
        f"Company: {entry.company or 'unknown'}\n\n"
        f"Body:\n{entry.body_text[:6000]}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    try:
        return llm.chat_structured(messages, EmailContext, temperature=0.1)
    except LLMConnectionError:
        return _fallback_context(entry)


def _fallback_context(entry: KnowledgeEntry) -> EmailContext:
    preview = entry.body_preview or entry.body_text[:400]
    return EmailContext(
        summary=f"{entry.subject}. {preview[:280]}".strip(),
        topics=[entry.domain_category] if entry.domain_category else [],
        action_items=[],
        entities=[entry.company] if entry.company else [],
    )


def _tokenize(query: str) -> list[str]:
    return [t for t in re.split(r"\W+", query.lower()) if len(t) >= 2]


def _snippet(text: str, terms: list[str], max_len: int = 220) -> str:
    if not text:
        return ""
    lower = text.lower()
    pos = -1
    for term in terms:
        idx = lower.find(term)
        if idx >= 0 and (pos < 0 or idx < pos):
            pos = idx
    if pos < 0:
        return text[:max_len] + ("…" if len(text) > max_len else "")
    start = max(0, pos - 60)
    chunk = text[start : start + max_len]
    prefix = "…" if start > 0 else ""
    suffix = "…" if start + max_len < len(text) else ""
    return prefix + chunk.strip() + suffix


def search_knowledge(
    query: str,
    *,
    limit: int = 25,
    domain: str = "",
    sender: str = "",
    knowledge_dir: Path | None = None,
) -> list[SearchHit]:
    """Full-text search over indexed emails and their context summaries."""
    if knowledge_dir:
        global INDEX_FILE
        INDEX_FILE = knowledge_dir / "emails.jsonl"

    terms = _tokenize(query)
    entries = list(load_entries().values())
    if domain:
        domain_key = domain.lower()
        entries = [e for e in entries if e.domain.lower() == domain_key]
    if sender:
        sender_key = sender.lower()
        entries = [e for e in entries if sender_key in e.sender_email.lower()]

    hits: list[SearchHit] = []
    for entry in entries:
        blob_parts = [
            entry.subject,
            entry.sender_email,
            entry.sender_name or "",
            entry.company or "",
            entry.body_text,
            entry.body_preview,
        ]
        if entry.context:
            blob_parts.extend(
                [
                    entry.context.summary,
                    " ".join(entry.context.topics),
                    " ".join(entry.context.entities),
                    " ".join(entry.context.action_items),
                ]
            )
        blob = " ".join(blob_parts).lower()
        if terms:
            score = sum(blob.count(t) * (3 if t in entry.subject.lower() else 1) for t in terms)
            if score <= 0:
                continue
        else:
            score = 1.0

        if entry.context and entry.context.summary:
            snippet_source = entry.context.summary
        else:
            snippet_source = entry.body_preview
        hits.append(
            SearchHit(
                score=float(score),
                entry=entry,
                snippet=_snippet(snippet_source or entry.body_text, terms),
            )
        )

    hits.sort(key=lambda h: (-h.score, h.entry.received_at), reverse=False)
    return hits[:limit]


def knowledge_stats(knowledge_dir: Path | None = None) -> dict[str, Any]:
    if knowledge_dir:
        global INDEX_FILE, MANIFEST_FILE
        INDEX_FILE = knowledge_dir / "emails.jsonl"
        MANIFEST_FILE = knowledge_dir / "manifest.yaml"

    entries = load_entries()
    manifest = load_manifest()
    stats = approval_stats()
    with_context = sum(1 for e in entries.values() if e.context_at)
    return {
        "entry_count": len(entries),
        "with_context": with_context,
        "without_context": len(entries) - with_context,
        "last_sync_at": manifest.last_sync_at,
        "last_sync_added": manifest.last_sync_added,
        "approved_domain_count": stats["approved_domain_count"],
        "approved_contact_count": stats["approved_contact_count"],
    }
