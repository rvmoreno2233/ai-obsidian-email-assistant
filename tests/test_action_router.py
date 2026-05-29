"""Tests for action router."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import yaml

from app.action_router import ActionRouter
from app.classifier import RuleBasedClassifier
from app.config import FIXTURES_DIR
from app.entity_matcher import load_catalogs, match_entities
from app.graph_client import MockGraphBackend
from app.obsidian_writer import ObsidianWriter
from app.response_queue import ResponseQueueStore
from app.responder import RuleBasedResponder
from app.rule_engine import RuleEngine
from app.schemas import NormalizedEmail
from tests.test_email_rules_yaml import EXAMPLE_RULES, EXAMPLE_TEMPLATES


def test_route_creates_draft_and_notes(tmp_path: Path, data_dir: Path):
    raw = json.loads((FIXTURES_DIR / "sample_emails.json").read_text())
    email = NormalizedEmail.model_validate(
        next(e for e in raw if e["message_id"] == "msg-needs-response")
    )
    catalogs = load_catalogs(data_dir)
    clf = RuleBasedClassifier(catalogs)
    entities = match_entities(email, catalogs)
    classification = clf.classify(email, entities)
    draft = RuleBasedResponder().draft(email, classification)

    writer = ObsidianWriter(tmp_path, data_dir=data_dir)
    router = ActionRouter(writer=writer, backend=MockGraphBackend())
    action = router.route(email, classification, draft, entity_match=entities)

    assert action.draft_created is True
    assert len(action.notes_written) > 0
    assert action.rule_matched is False


def test_route_rule_engine_short_circuits_legacy_draft(tmp_path: Path, data_dir: Path):
    rules_path = tmp_path / "email_rules.yaml"
    templates_path = tmp_path / "response_templates.yaml"
    rules_path.write_text(yaml.dump(EXAMPLE_RULES, sort_keys=False), encoding="utf-8")
    templates_path.write_text(yaml.dump(EXAMPLE_TEMPLATES, sort_keys=False), encoding="utf-8")

    email = NormalizedEmail.model_validate(
        {
            "message_id": "msg-capturerx",
            "subject": "CaptureRx ticket follow-up",
            "sender_name": "Jane Doe",
            "sender_email": "jane.doe@acmehealth.com",
            "received_at": "2026-05-29T12:00:00Z",
            "body_text": "Please review ticket 12345.",
        }
    )
    catalogs = load_catalogs(data_dir)
    entities = match_entities(email, catalogs)
    classification = RuleBasedClassifier(catalogs).classify(email, entities)
    draft = RuleBasedResponder().draft(email, classification)

    queue_dir = tmp_path / "queue"
    mock_llm = MagicMock()
    mock_llm.chat_text.return_value = "Acknowledged."
    rule_engine = RuleEngine(
        backend=MockGraphBackend(),
        queue_store=ResponseQueueStore(queue_dir),
        enabled=True,
        catalogs=catalogs,
        rules_path=rules_path,
        templates_path=templates_path,
        team_name="Test Team",
        llm=mock_llm,
    )
    router = ActionRouter(
        writer=None,
        backend=MockGraphBackend(),
        rule_engine=rule_engine,
    )
    action = router.route(email, classification, draft, entity_match=entities)

    assert action.rule_matched is True
    assert action.rule_id == "capturerx_ack"
    assert action.draft_created is True
    assert action.queue_entry_id is not None
    assert len(ResponseQueueStore(queue_dir).list_entries("approval")) == 1

