"""Pydantic models and YAML I/O for email response rules and templates."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from app.config import DATA_DIR

EMAIL_RULES_FILE = DATA_DIR / "email_rules.yaml"
RESPONSE_TEMPLATES_FILE = DATA_DIR / "response_templates.yaml"

MatchScope = Literal["subject_only", "body_only", "subject_or_body", "subject_and_body"]
MatchMode = Literal["any", "all"]
GenerationMode = Literal["canned", "llm"]
DeliveryMode = Literal["approval", "auto"]
TemplateCreatedBy = Literal["manual", "ai_assist"]


class RuleMatchConfig(BaseModel):
    """Keyword matching configuration for a response rule."""

    subject_keywords: list[str] = Field(default_factory=list)
    body_keywords: list[str] = Field(default_factory=list)
    scope: MatchScope = "subject_or_body"
    mode: MatchMode = "any"


class EmailRule(BaseModel):
    """Keyword-triggered auto-response rule."""

    id: str
    name: str
    enabled: bool = True
    match: RuleMatchConfig = Field(default_factory=RuleMatchConfig)
    template_id: str
    generation: GenerationMode = "canned"
    delivery: DeliveryMode = "approval"
    append_to_existing_note: bool = True


class EmailRulesCatalog(BaseModel):
    """Top-level container for email_rules.yaml."""

    rules: list[EmailRule] = Field(default_factory=list)


class ResponseTemplate(BaseModel):
    """Canned or LLM-assisted reply template."""

    id: str
    name: str
    subject_prefix: str = "Re: "
    body: str = ""
    ai_instructions: str = ""
    created_by: TemplateCreatedBy = "manual"


class ResponseTemplatesCatalog(BaseModel):
    """Top-level container for response_templates.yaml."""

    templates: list[ResponseTemplate] = Field(default_factory=list)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _save_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def load_rules(path: Path | None = None) -> EmailRulesCatalog:
    """Load rules from YAML; returns empty catalog when file is missing."""
    raw = _load_yaml(path or EMAIL_RULES_FILE)
    if not raw:
        return EmailRulesCatalog()
    return EmailRulesCatalog.model_validate(raw)


def save_rules(catalog: EmailRulesCatalog, path: Path | None = None) -> None:
    """Persist rules catalog to YAML."""
    _save_yaml(path or EMAIL_RULES_FILE, catalog.model_dump())


def load_templates(path: Path | None = None) -> ResponseTemplatesCatalog:
    """Load templates from YAML; returns empty catalog when file is missing."""
    raw = _load_yaml(path or RESPONSE_TEMPLATES_FILE)
    if not raw:
        return ResponseTemplatesCatalog()
    return ResponseTemplatesCatalog.model_validate(raw)


def save_templates(catalog: ResponseTemplatesCatalog, path: Path | None = None) -> None:
    """Persist templates catalog to YAML."""
    _save_yaml(path or RESPONSE_TEMPLATES_FILE, catalog.model_dump())


def get_rule(rule_id: str, path: Path | None = None) -> EmailRule | None:
    """Return a single rule by id, if present."""
    for rule in load_rules(path).rules:
        if rule.id == rule_id:
            return rule
    return None


def get_template(template_id: str, path: Path | None = None) -> ResponseTemplate | None:
    """Return a single template by id, if present."""
    for template in load_templates(path).templates:
        if template.id == template_id:
            return template
    return None


def add_rule(rule: EmailRule, path: Path | None = None) -> EmailRule:
    """Append a rule; raises ValueError when id already exists."""
    catalog = load_rules(path)
    if get_rule(rule.id, path):
        msg = f"Rule already exists: {rule.id}"
        raise ValueError(msg)
    catalog.rules.append(rule)
    save_rules(catalog, path)
    return rule


def update_rule(rule_id: str, patch: dict, path: Path | None = None) -> EmailRule | None:
    """Merge patch into an existing rule by id."""
    catalog = load_rules(path)
    for index, rule in enumerate(catalog.rules):
        if rule.id == rule_id:
            updated = rule.model_copy(update=patch)
            catalog.rules[index] = updated
            save_rules(catalog, path)
            return updated
    return None


def delete_rule(rule_id: str, path: Path | None = None) -> bool:
    """Remove a rule by id; returns False when not found."""
    catalog = load_rules(path)
    original_len = len(catalog.rules)
    catalog.rules = [rule for rule in catalog.rules if rule.id != rule_id]
    if len(catalog.rules) == original_len:
        return False
    save_rules(catalog, path)
    return True


def add_template(template: ResponseTemplate, path: Path | None = None) -> ResponseTemplate:
    """Append a template; raises ValueError when id already exists."""
    if get_template(template.id, path):
        msg = f"Template already exists: {template.id}"
        raise ValueError(msg)
    catalog = load_templates(path)
    catalog.templates.append(template)
    save_templates(catalog, path)
    return template


def update_template(
    template_id: str,
    patch: dict,
    path: Path | None = None,
) -> ResponseTemplate | None:
    """Merge patch into an existing template by id."""
    catalog = load_templates(path)
    for index, template in enumerate(catalog.templates):
        if template.id == template_id:
            updated = template.model_copy(update=patch)
            catalog.templates[index] = updated
            save_templates(catalog, path)
            return updated
    return None


def delete_template(template_id: str, path: Path | None = None) -> bool:
    """Remove a template by id; returns False when not found."""
    catalog = load_templates(path)
    original_len = len(catalog.templates)
    catalog.templates = [t for t in catalog.templates if t.id != template_id]
    if len(catalog.templates) == original_len:
        return False
    save_templates(catalog, path)
    return True
