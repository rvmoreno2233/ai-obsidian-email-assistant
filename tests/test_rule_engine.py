"""Tests for keyword rule engine matching, rendering, and queue routing."""

from pathlib import Path
from unittest.mock import MagicMock

import yaml

from app.email_rules import EmailRulesCatalog, ResponseTemplatesCatalog, save_rules, save_templates
from app.entity_matcher import Catalogs, load_catalogs, match_entities
from app.graph_client import MockGraphBackend
from app.obsidian_writer import ObsidianWriter
from app.response_queue import ResponseQueueStore
from app.rule_engine import (
    RuleEngine,
    fill_template_with_llm,
    match_rules,
    passes_contact_importance_gate,
    render_template,
    rule_matches,
    sender_first_name,
)
from app.schemas import ContactRecord, ContactsCatalog, EmailClassification, NormalizedEmail
from tests.test_email_rules_yaml import EXAMPLE_RULES, EXAMPLE_TEMPLATES


def _write_rules(path: Path, payload: dict | None = None) -> Path:
    rules_path = path / "email_rules.yaml"
    rules_path.write_text(yaml.dump(payload or EXAMPLE_RULES, sort_keys=False), encoding="utf-8")
    return rules_path


def _write_templates(path: Path, payload: dict | None = None) -> Path:
    templates_path = path / "response_templates.yaml"
    templates_path.write_text(
        yaml.dump(payload or EXAMPLE_TEMPLATES, sort_keys=False),
        encoding="utf-8",
    )
    return templates_path


def _sample_email(**overrides) -> NormalizedEmail:
    base = {
        "message_id": "msg-rule-test",
        "subject": "CaptureRx ticket update",
        "sender_name": "Jane Doe",
        "sender_email": "jane.doe@acmehealth.com",
        "received_at": "2026-05-29T12:00:00Z",
        "body_text": "Please review ticket 12345 for CaptureRx.",
    }
    base.update(overrides)
    return NormalizedEmail.model_validate(base)


def test_sender_first_name_from_display_name():
    email = _sample_email(sender_name="Jane Doe")
    assert sender_first_name(email) == "Jane"


def test_match_rules_subject_or_body_any(tmp_path: Path):
    rules_path = _write_rules(tmp_path)
    email = _sample_email(subject="Unrelated", body_text="CaptureRx ticket is ready")
    rule = match_rules(email, rules_path=rules_path)
    assert rule is not None
    assert rule.id == "capturerx_ack"


def test_rule_matches_subject_only(tmp_path: Path):
    payload = {
        "rules": [
            {
                **EXAMPLE_RULES["rules"][0],
                "match": {
                    "subject_keywords": ["capturerx"],
                    "body_keywords": ["ignored"],
                    "scope": "subject_only",
                    "mode": "any",
                },
            }
        ]
    }
    rules_path = _write_rules(tmp_path, payload)
    catalog = EmailRulesCatalog.model_validate(yaml.safe_load(rules_path.read_text()))
    rule = catalog.rules[0]

    assert rule_matches(_sample_email(subject="CaptureRx update", body_text="ignored"), rule)
    assert not rule_matches(_sample_email(subject="Other", body_text="CaptureRx"), rule)


def test_rule_matches_body_only(tmp_path: Path):
    payload = {
        "rules": [
            {
                **EXAMPLE_RULES["rules"][0],
                "match": {
                    "subject_keywords": ["ignored"],
                    "body_keywords": ["ticket"],
                    "scope": "body_only",
                    "mode": "any",
                },
            }
        ]
    }
    catalog = EmailRulesCatalog.model_validate(yaml.safe_load(_write_rules(tmp_path, payload).read_text()))
    rule = catalog.rules[0]

    assert rule_matches(_sample_email(subject="Hello", body_text="ticket 99"), rule)
    assert not rule_matches(_sample_email(subject="ticket in subject", body_text="plain"), rule)


def test_rule_matches_subject_and_body(tmp_path: Path):
    payload = {
        "rules": [
            {
                **EXAMPLE_RULES["rules"][0],
                "match": {
                    "subject_keywords": ["capturerx"],
                    "body_keywords": ["ticket"],
                    "scope": "subject_and_body",
                    "mode": "all",
                },
            }
        ]
    }
    catalog = EmailRulesCatalog.model_validate(yaml.safe_load(_write_rules(tmp_path, payload).read_text()))
    rule = catalog.rules[0]

    assert rule_matches(_sample_email(subject="CaptureRx update", body_text="ticket 123"), rule)
    assert not rule_matches(_sample_email(subject="CaptureRx update", body_text="no match"), rule)


def test_render_template_substitutes_placeholders():
    template = ResponseTemplatesCatalog.model_validate(EXAMPLE_TEMPLATES).templates[0]
    body = render_template(
        template,
        sender_first="Jane",
        team_name="Creo 340B",
        ai_response="We received your request.",
    )
    assert "Hi Jane," in body
    assert "We received your request." in body
    assert "Best, Creo 340B" in body


def test_fill_template_with_llm_mock():
    template = ResponseTemplatesCatalog.model_validate(EXAMPLE_TEMPLATES).templates[0]
    email = _sample_email()
    mock_llm = MagicMock()
    mock_llm.chat_text.return_value = "Thanks for the update."

    text = fill_template_with_llm(template, email, llm=mock_llm)
    assert text == "Thanks for the update."
    mock_llm.chat_text.assert_called_once()


def test_importance_gate_blocks_low_importance(data_dir: Path):
    contacts_path = data_dir / "contacts.yaml"
    contacts = ContactsCatalog.model_validate(yaml.safe_load(contacts_path.read_text()))
    contacts.contacts.append(
        ContactRecord(
            name="Low Contact",
            email="low.contact@example.com",
            importance="low",
        )
    )
    contacts_path.write_text(
        yaml.dump(contacts.model_dump(), sort_keys=False),
        encoding="utf-8",
    )
    catalogs = load_catalogs(data_dir)
    email = _sample_email(sender_email="low.contact@example.com")
    entity_match = match_entities(email, catalogs)

    assert passes_contact_importance_gate(email, entity_match, catalogs) is False


def test_process_email_canned_approval_queue(tmp_path: Path, data_dir: Path, tmp_vault: Path):
    rules_path = _write_rules(tmp_path)
    templates_path = _write_templates(tmp_path)
    canned_payload = {
        "rules": [
            {
                **EXAMPLE_RULES["rules"][0],
                "generation": "canned",
                "delivery": "approval",
            }
        ]
    }
    rules_path.write_text(yaml.dump(canned_payload, sort_keys=False), encoding="utf-8")

    queue_dir = tmp_path / "queue"
    backend = MockGraphBackend()
    writer = ObsidianWriter(tmp_vault, data_dir=data_dir)
    engine = RuleEngine(
        backend=backend,
        writer=writer,
        queue_store=ResponseQueueStore(queue_dir),
        enabled=True,
        catalogs=load_catalogs(data_dir),
        rules_path=rules_path,
        templates_path=templates_path,
        team_name="Test Team",
    )
    email = _sample_email()
    entity_match = match_entities(email, engine.catalogs)
    classification = EmailClassification(
        category="needs_response",
        priority="high",
        confidence=0.9,
        company="Acme Health",
        contact="Jane Doe",
        summary="Needs reply",
        reason="test",
    )

    result = engine.process_email(email, classification, entity_match)
    assert result is not None
    assert result.matched is True
    assert result.rule_id == "capturerx_ack"
    assert result.queue_name == "approval"
    assert result.queue_entry_id is not None
    assert result.draft_id is not None
    assert "Hi Jane," in (result.body or "")

    store = ResponseQueueStore(queue_dir)
    approval = store.list_entries("approval")
    assert len(approval) == 1
    assert approval[0].rule_id == "capturerx_ack"
    assert len(store.list_log()) == 1


def test_process_email_llm_auto_queue(tmp_path: Path, data_dir: Path):
    rules_path = _write_rules(tmp_path)
    templates_path = _write_templates(tmp_path)
    auto_payload = {
        "rules": [
            {
                **EXAMPLE_RULES["rules"][0],
                "generation": "llm",
                "delivery": "auto",
                "append_to_existing_note": False,
            }
        ]
    }
    rules_path.write_text(yaml.dump(auto_payload, sort_keys=False), encoding="utf-8")

    mock_llm = MagicMock()
    mock_llm.chat_text.return_value = "Acknowledged and reviewing."
    queue_dir = tmp_path / "queue"
    engine = RuleEngine(
        backend=MockGraphBackend(),
        queue_store=ResponseQueueStore(queue_dir),
        llm=mock_llm,
        enabled=True,
        catalogs=load_catalogs(data_dir),
        rules_path=rules_path,
        templates_path=templates_path,
        team_name="Test Team",
    )
    email = _sample_email()
    entity_match = match_entities(email, engine.catalogs)
    classification = EmailClassification(
        category="needs_response",
        priority="medium",
        confidence=0.8,
        summary="Needs reply",
        reason="test",
    )

    result = engine.process_email(email, classification, entity_match)
    assert result is not None
    assert result.queue_name == "auto"
    assert "Acknowledged and reviewing." in (result.body or "")
    assert len(ResponseQueueStore(queue_dir).list_entries("auto")) == 1


def test_process_email_disabled_returns_none(data_dir: Path, tmp_path: Path):
    engine = RuleEngine(
        backend=MockGraphBackend(),
        enabled=False,
        catalogs=load_catalogs(data_dir),
        rules_path=_write_rules(tmp_path),
        templates_path=_write_templates(tmp_path),
    )
    email = _sample_email()
    entity_match = match_entities(email, engine.catalogs)
    classification = EmailClassification(
        category="needs_response",
        priority="high",
        confidence=0.9,
        summary="Needs reply",
        reason="test",
    )
    assert engine.process_email(email, classification, entity_match) is None
