"""Tests for Pydantic schema validation."""

import pytest
from pydantic import ValidationError

from app.schemas import (
    DraftResponse,
    EmailClassification,
    NormalizedEmail,
    RoutedAction,
    WaitingItem,
    WaitingItemMatch,
)


def test_normalized_email_valid():
    email = NormalizedEmail(
        message_id="msg-1",
        subject="Hello",
        sender_email="jane@acmehealth.com",
        received_at="2026-05-24T10:00:00Z",
        body_text="Test body",
    )
    assert email.sender_name is None
    assert email.message_id == "msg-1"


def test_classification_confidence_bounds():
    with pytest.raises(ValidationError):
        EmailClassification(
            category="fyi",
            priority="low",
            confidence=1.5,
            summary="x",
            reason="y",
        )


def test_classification_valid():
    c = EmailClassification(
        category="needs_response",
        priority="high",
        confidence=0.9,
        summary="Needs reply",
        reason="Direct question",
        needs_human_review=True,
    )
    assert c.category == "needs_response"


def test_waiting_item_match():
    m = WaitingItemMatch(
        waiting_item_id="acme_schema_approval",
        matched=True,
        evidence="schema approved",
        confidence=0.95,
    )
    assert m.matched is True


def test_draft_response_defaults():
    d = DraftResponse(should_reply=False, reason="No reply needed")
    assert d.auto_send_allowed is False


def test_routed_action():
    r = RoutedAction(message_id="msg-1", notes_written=["Companies/Acme Health.md"])
    assert len(r.notes_written) == 1


def test_waiting_item_status():
    w = WaitingItem(
        id="test_item",
        project="Test",
        status="open",
    )
    assert w.status == "open"
