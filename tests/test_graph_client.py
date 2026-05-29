"""Tests for email backends."""

from app.graph_client import MockGraphBackend
from app.ingestion import load_recent_emails
from app.schemas import NormalizedEmail


def test_mock_backend_lists_emails():
    backend = MockGraphBackend()
    emails = backend.list_recent_messages()
    assert len(emails) >= 8
    assert all(isinstance(e, NormalizedEmail) for e in emails)


def test_mock_create_reply_draft():
    backend = MockGraphBackend()
    emails = backend.list_recent_messages(top=1)
    draft_id = backend.create_reply_draft(
        emails[0].message_id,
        "Re: test",
        "Thanks for your email.",
    )
    assert draft_id is not None
    assert draft_id.startswith("draft-")


def test_load_recent_emails_via_ingestion():
    emails = load_recent_emails(MockGraphBackend())
    assert len(emails) > 0
