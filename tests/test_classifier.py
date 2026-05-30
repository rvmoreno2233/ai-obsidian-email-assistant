"""Tests for rule-based classifier."""

import json

import pytest

from app.classifier import RuleBasedClassifier
from app.config import DATA_DIR, FIXTURES_DIR
from app.entity_matcher import load_catalogs, match_entities
from app.schemas import NormalizedEmail

FIXTURE_PATH = FIXTURES_DIR / "sample_emails.json"

EXPECTED = {
    "msg-schema-approval": "waiting_info_arrived",
    "msg-newsletter": "newsletter",
    "msg-invoice": "invoice_or_admin",
    "msg-meeting": "meeting_request",
    "msg-needs-response": "needs_response",
    "msg-project-update": "project_update",
    "msg-waiting-northstar": "waiting_info_arrived",
    "msg-fyi": "fyi",
    "msg-ooo": "ignore_low_priority",
    "msg-ignore-marketing": "newsletter",
}


@pytest.fixture
def classifier():
    return RuleBasedClassifier(load_catalogs(DATA_DIR))


@pytest.fixture
def emails() -> list[NormalizedEmail]:
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return [NormalizedEmail.model_validate(e) for e in raw]


@pytest.mark.parametrize("message_id,expected_category", list(EXPECTED.items()))
def test_classify_fixtures(classifier, emails, message_id, expected_category):
    email = next(e for e in emails if e.message_id == message_id)
    entities = match_entities(email, classifier.catalogs)
    result = classifier.classify(email, entities)
    assert (
        result.category == expected_category
    ), f"{message_id}: expected {expected_category}, got {result.category} ({result.reason})"
