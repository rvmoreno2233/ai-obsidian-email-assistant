"""Route classified emails to Obsidian, drafts, and notifications."""

from __future__ import annotations

import logging

from app.config import AUTO_SEND_MODE, AutoSendMode
from app.graph_client import EmailBackend
from app.obsidian_writer import ObsidianWriter
from app.schemas import (
    DraftResponse,
    EmailClassification,
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
    ) -> None:
        self.writer = writer
        self.backend = backend
        self.auto_send_mode = auto_send_mode or AUTO_SEND_MODE

    def route(
        self,
        email: NormalizedEmail,
        classification: EmailClassification,
        draft: DraftResponse,
    ) -> RoutedAction:
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
