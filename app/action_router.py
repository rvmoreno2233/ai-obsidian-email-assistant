"""Route classified emails to Obsidian, drafts, and notifications."""

from __future__ import annotations

import logging

from app.config import AUTO_SEND_MODE, AutoSendMode
from app.graph_client import EmailBackend
from app.obsidian_writer import ObsidianWriter
from app.rule_engine import RuleEngine, RuleEngineResult
from app.schemas import (
    DraftResponse,
    EmailClassification,
    EntityMatchResult,
    NormalizedEmail,
    RoutedAction,
)

logger = logging.getLogger(__name__)


class ActionRouter:
    """Execute post-classification actions."""

    def __init__(
        self,
        writer: ObsidianWriter | None,
        backend: EmailBackend,
        auto_send_mode: AutoSendMode | None = None,
        rule_engine: RuleEngine | None = None,
    ) -> None:
        self.writer = writer
        self.backend = backend
        self.auto_send_mode = auto_send_mode or AUTO_SEND_MODE
        self.rule_engine = rule_engine

    def _route_rule_match(
        self,
        email: NormalizedEmail,
        classification: EmailClassification,
        result: RuleEngineResult,
    ) -> RoutedAction:
        action = RoutedAction(
            message_id=email.message_id,
            rule_matched=True,
            rule_id=result.rule_id,
            queue_entry_id=result.queue_entry_id,
        )

        if result.thread_note:
            action.notes_written.append(result.thread_note)

        if result.draft_id:
            action.draft_created = True
            action.draft_location = result.draft_id
        elif self.writer:
            action.draft_location = "Email Assistant/Draft Replies.md"

        if result.rule_id:
            queue_label = result.queue_name or "approval"
            action.notifications.append(
                f"Rule matched ({result.rule_id}) — queued for {queue_label}"
            )

        if classification.priority in ("high", "urgent"):
            action.notifications.append(f"High priority: {email.subject}")

        action.errors.extend(result.errors)
        return action

    def route(
        self,
        email: NormalizedEmail,
        classification: EmailClassification,
        draft: DraftResponse,
        entity_match: EntityMatchResult | None = None,
    ) -> RoutedAction:
        if self.rule_engine and entity_match is not None:
            rule_result = self.rule_engine.process_email(email, classification, entity_match)
            if rule_result and rule_result.matched:
                return self._route_rule_match(email, classification, rule_result)

        action = RoutedAction(message_id=email.message_id)

        if self.writer:
            try:
                notes = self.writer.write_email_summary(email, classification, draft)
                action.notes_written.extend(notes)
            except Exception as e:
                action.errors.append(f"Obsidian write failed: {e}")
                logger.exception("Obsidian write failed")

        if classification.category == "waiting_info_arrived":
            action.notifications.append(
                f"Waiting info may have arrived: {email.subject}"
            )
            if self.writer:
                for item_id in classification.keywords:
                    try:
                        self.writer.mark_waiting_item_complete(
                            item_id,
                            classification.summary,
                        )
                        action.waiting_items_closed.append(item_id)
                    except Exception as e:
                        action.errors.append(str(e))

        if draft.should_reply:
            if self.auto_send_mode != AutoSendMode.OFF and draft.auto_send_allowed:
                action.errors.append("Auto-send blocked in MVP")
            else:
                try:
                    draft_id = self.backend.create_reply_draft(
                        email.message_id,
                        draft.subject or f"Re: {email.subject}",
                        draft.body or "",
                    )
                    if draft_id:
                        action.draft_created = True
                        action.draft_location = draft_id
                    elif self.writer:
                        action.draft_location = "Email Assistant/Draft Replies.md"
                except Exception as e:
                    action.errors.append(f"Draft creation failed: {e}")
                    logger.exception("Draft creation failed")

        if classification.priority in ("high", "urgent"):
            action.notifications.append(f"High priority: {email.subject}")

        return action
