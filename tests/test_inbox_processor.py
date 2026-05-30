"""Tests for inbox_processor cursor and pipeline helpers."""

from __future__ import annotations

from app.inbox_processor import emails_since_cursor
from app.schemas import NormalizedEmail


def _email(message_id: str) -> NormalizedEmail:
    return NormalizedEmail(
        message_id=message_id,
        subject=f"Subject {message_id}",
        sender_name="Test",
        sender_email="test@example.com",
        received_at="2026-05-30T12:00:00Z",
        body_text="body",
    )


def test_emails_since_cursor_empty_list():
    assert emails_since_cursor([], "msg-1") == []


def test_emails_since_cursor_no_cursor_returns_oldest_first():
    emails = [_email("msg-3"), _email("msg-2"), _email("msg-1")]
    result = emails_since_cursor(emails, None)
    assert [e.message_id for e in result] == ["msg-1", "msg-2", "msg-3"]


def test_emails_since_cursor_after_known_message():
    emails = [_email("msg-3"), _email("msg-2"), _email("msg-1")]
    result = emails_since_cursor(emails, "msg-1")
    assert [e.message_id for e in result] == ["msg-2", "msg-3"]


def test_emails_since_cursor_unknown_cursor_returns_all_oldest_first():
    emails = [_email("msg-2"), _email("msg-1")]
    result = emails_since_cursor(emails, "msg-missing")
    assert [e.message_id for e in result] == ["msg-1", "msg-2"]
