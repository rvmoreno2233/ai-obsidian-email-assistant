"""Tests for email rules and response template YAML I/O."""

from pathlib import Path

import pytest
import yaml

from app.email_rules import (
    EmailRule,
    EmailRulesCatalog,
    ResponseTemplate,
    ResponseTemplatesCatalog,
    get_rule,
    get_template,
    load_rules,
    load_templates,
    save_rules,
    save_templates,
)

EXAMPLE_RULES = {
    "rules": [
        {
            "id": "capturerx_ack",
            "name": "CaptureRx acknowledgements",
            "enabled": True,
            "match": {
                "subject_keywords": ["capturerx", "ticket"],
                "body_keywords": [],
                "scope": "subject_or_body",
                "mode": "any",
            },
            "template_id": "ack_template",
            "generation": "llm",
            "delivery": "approval",
            "append_to_existing_note": True,
        }
    ]
}

EXAMPLE_TEMPLATES = {
    "templates": [
        {
            "id": "ack_template",
            "name": "Generic acknowledgement",
            "subject_prefix": "Re: ",
            "body": (
                "Hi {sender_first_name},\n"
                "Thanks for your email. {ai_response}\n"
                "Best, {team_name}\n"
            ),
            "ai_instructions": (
                "One short paragraph confirming receipt and committing to a next step."
            ),
            "created_by": "ai_assist",
        }
    ]
}


def test_load_rules_empty_when_missing(tmp_path: Path):
    path = tmp_path / "email_rules.yaml"
    catalog = load_rules(path)
    assert catalog.rules == []


def test_example_rules_validate():
    catalog = EmailRulesCatalog.model_validate(EXAMPLE_RULES)
    assert len(catalog.rules) == 1
    rule = catalog.rules[0]
    assert rule.id == "capturerx_ack"
    assert rule.match.subject_keywords == ["capturerx", "ticket"]
    assert rule.generation == "llm"
    assert rule.delivery == "approval"


def test_example_templates_validate():
    catalog = ResponseTemplatesCatalog.model_validate(EXAMPLE_TEMPLATES)
    assert len(catalog.templates) == 1
    template = catalog.templates[0]
    assert template.id == "ack_template"
    assert "{sender_first_name}" in template.body
    assert template.created_by == "ai_assist"


def test_rules_round_trip(tmp_path: Path):
    path = tmp_path / "email_rules.yaml"
    catalog = EmailRulesCatalog.model_validate(EXAMPLE_RULES)
    save_rules(catalog, path)

    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded == EXAMPLE_RULES

    reloaded = load_rules(path)
    assert reloaded.model_dump() == catalog.model_dump()
    assert get_rule("capturerx_ack", path) is not None
    assert get_rule("missing", path) is None


def test_templates_round_trip(tmp_path: Path):
    path = tmp_path / "response_templates.yaml"
    catalog = ResponseTemplatesCatalog.model_validate(EXAMPLE_TEMPLATES)
    save_templates(catalog, path)

    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded == EXAMPLE_TEMPLATES

    reloaded = load_templates(path)
    assert reloaded.model_dump() == catalog.model_dump()
    assert get_template("ack_template", path) is not None
    assert get_template("missing", path) is None


def test_invalid_rule_scope_rejected():
    bad = {
        "rules": [
            {
                "id": "bad",
                "name": "Bad rule",
                "template_id": "t1",
                "match": {"scope": "invalid_scope"},
            }
        ]
    }
    with pytest.raises(Exception):
        EmailRulesCatalog.model_validate(bad)
