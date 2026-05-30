"""Tests for entity_matcher."""

import json

import pytest

from app.config import FIXTURES_DIR
from app.entity_matcher import load_catalogs, match_entities, match_waiting_items
from app.schemas import NormalizedEmail

FIXTURE_PATH = FIXTURES_DIR / "sample_emails.json"


@pytest.fixture
def catalogs(fixture_catalog_dir):
    return load_catalogs(fixture_catalog_dir)


@pytest.fixture
def emails() -> list[NormalizedEmail]:
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return [NormalizedEmail.model_validate(e) for e in raw]


def test_match_acme_company(emails, catalogs):
    schema_email = next(e for e in emails if e.message_id == "msg-schema-approval")
    result = match_entities(schema_email, catalogs)
    assert result.company == "Acme Health"
    assert result.contact == "Jane Doe"
    assert "Acme Data Pipeline" in result.projects


def test_waiting_item_match(emails, catalogs):
    schema_email = next(e for e in emails if e.message_id == "msg-schema-approval")
    waiting = match_waiting_items(schema_email, catalogs)
    acme_match = next(w for w in waiting if w.waiting_item_id == "acme_schema_approval")
    assert acme_match.matched is True
    assert acme_match.confidence > 0.5


def test_northstar_refresh_waiting(emails, catalogs):
    refresh_email = next(e for e in emails if e.message_id == "msg-waiting-northstar")
    waiting = match_waiting_items(refresh_email, catalogs)
    ns_match = next(w for w in waiting if w.waiting_item_id == "northstar_refresh_timing")
    assert ns_match.matched is True
