"""Shared inbox processing pipeline for CLI, Studio jobs, and background poller."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.action_router import ActionRouter
from app.classifier import classify_email, get_classifier
from app.config import OBSIDIAN_VAULT_PATH, RULE_ENGINE_ENABLED
from app.entity_matcher import match_entities
from app.graph_client import EmailBackend, get_email_backend
from app.ingestion import load_recent_emails
from app.obsidian_writer import ObsidianWriter
from app.responder import draft_response, get_responder
from app.rule_engine import RuleEngine
from app.schemas import NormalizedEmail, RoutedAction

logger = logging.getLogger(__name__)


@dataclass
class ProcessedEmail:
    """Summary of one email processed through the pipeline."""

    message_id: str
    subject: str
    category: str
    priority: str
    draft_created: bool
    rule_id: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class InboxProcessResult:
    """Aggregate result from a process_inbox run."""

    processed: int
    last_message_id: str | None
    emails: list[ProcessedEmail] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "processed": self.processed,
            "last_message_id": self.last_message_id,
            "errors": self.errors,
            "emails": [
                {
                    "message_id": e.message_id,
                    "subject": e.subject,
                    "category": e.category,
                    "priority": e.priority,
                    "draft_created": e.draft_created,
                    "rule_id": e.rule_id,
                    "errors": e.errors,
                }
                for e in self.emails
            ],
        }


def emails_since_cursor(
    emails: list[NormalizedEmail],
    cursor: str | None,
) -> list[NormalizedEmail]:
    """Return new emails (oldest-first) since the poller cursor.

    ``emails`` is expected newest-first from the backend.
    """
    if not emails:
        return []
    if not cursor:
        return list(reversed(emails))

    new_emails: list[NormalizedEmail] = []
    for email in emails:
        if email.message_id == cursor:
            break
        new_emails.append(email)
    return list(reversed(new_emails))


def build_pipeline(
    backend: EmailBackend | None = None,
    vault_path: str | Path | None = None,
    rule_engine_enabled: bool | None = None,
) -> tuple[EmailBackend, ActionRouter, ObsidianWriter | None]:
    """Construct backend, optional vault writer, and action router."""
    be = backend or get_email_backend()
    writer: ObsidianWriter | None = None
    path = vault_path if vault_path is not None else OBSIDIAN_VAULT_PATH
    if path:
        vault = Path(path)
        vault.mkdir(parents=True, exist_ok=True)
        writer = ObsidianWriter(vault)

    enabled = RULE_ENGINE_ENABLED if rule_engine_enabled is None else rule_engine_enabled
    rule_engine = RuleEngine(backend=be, writer=writer) if enabled else None
    router = ActionRouter(writer=writer, backend=be, rule_engine=rule_engine)
    return be, router, writer


def process_inbox(
    *,
    backend: EmailBackend | None = None,
    router: ActionRouter | None = None,
    top: int = 25,
    since_message_id: str | None = None,
    rule_engine_enabled: bool | None = None,
    vault_path: str | Path | None = None,
) -> InboxProcessResult:
    """Process recent inbox messages through classify + route pipeline."""
    be, built_router, _writer = build_pipeline(
        backend=backend,
        vault_path=vault_path,
        rule_engine_enabled=rule_engine_enabled,
    )
    active_router = router or built_router
    classifier = get_classifier()
    responder = get_responder()

    recent = load_recent_emails(be, top=top)
    to_process = emails_since_cursor(recent, since_message_id)

    result = InboxProcessResult(processed=0, last_message_id=since_message_id)
    if recent and not since_message_id:
        result.last_message_id = recent[0].message_id
    elif recent:
        result.last_message_id = recent[0].message_id

    for email in to_process:
        try:
            entity_match = match_entities(email)
            classification = classify_email(email, entity_match, classifier)
            response = draft_response(email, classification, responder)
            action = active_router.route(
                email,
                classification,
                response,
                entity_match=entity_match,
            )
            summary = _summarize_email(
                email,
                classification.category,
                classification.priority,
                action,
            )
            result.emails.append(summary)
            result.processed += 1
        except Exception as exc:
            logger.exception("Failed processing message %s", email.message_id)
            result.errors.append(f"{email.message_id}: {exc}")
            result.emails.append(
                ProcessedEmail(
                    message_id=email.message_id,
                    subject=email.subject,
                    category="error",
                    priority="low",
                    draft_created=False,
                    errors=[str(exc)],
                )
            )

    if recent:
        result.last_message_id = recent[0].message_id

    return result


def _summarize_email(
    email: NormalizedEmail,
    category: str,
    priority: str,
    action: RoutedAction,
) -> ProcessedEmail:
    return ProcessedEmail(
        message_id=email.message_id,
        subject=email.subject,
        category=category,
        priority=priority,
        draft_created=action.draft_created,
        rule_id=action.rule_id,
        errors=list(action.errors),
    )
