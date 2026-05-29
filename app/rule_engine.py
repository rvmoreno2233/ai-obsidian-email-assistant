"""Keyword rule matching, template rendering, and queue routing for auto-response."""

from __future__ import annotations

import logging
from pathlib import Path

from app.classifier import RuleBasedClassifier
from app.config import PROMPTS_DIR, RULE_ENGINE_ENABLED
from app.email_rules import (
    EMAIL_RULES_FILE,
    RESPONSE_TEMPLATES_FILE,
    EmailRule,
    EmailRulesCatalog,
    MatchMode,
    ResponseTemplate,
    get_template,
    load_rules,
)
from app.entity_matcher import Catalogs, load_catalogs
from app.graph_client import EmailBackend
from app.llm_client import OllamaClient
from app.obsidian_writer import ObsidianWriter
from app.response_queue import QueueEntry, QueueName, ResponseQueueStore
from app.schemas import DraftResponse, EmailClassification, EntityMatchResult, NormalizedEmail
from app.team_config import load_team_config

logger = logging.getLogger(__name__)


class RuleEngineResult:
    """Outcome of rule engine processing for one email."""

    __slots__ = (
        "matched",
        "rule_id",
        "template_id",
        "queue_name",
        "queue_entry_id",
        "subject",
        "body",
        "thread_note",
        "draft_id",
        "errors",
    )

    def __init__(
        self,
        *,
        matched: bool = False,
        rule_id: str | None = None,
        template_id: str | None = None,
        queue_name: QueueName | None = None,
        queue_entry_id: str | None = None,
        subject: str | None = None,
        body: str | None = None,
        thread_note: str | None = None,
        draft_id: str | None = None,
        errors: list[str] | None = None,
    ) -> None:
        self.matched = matched
        self.rule_id = rule_id
        self.template_id = template_id
        self.queue_name = queue_name
        self.queue_entry_id = queue_entry_id
        self.subject = subject
        self.body = body
        self.thread_note = thread_note
        self.draft_id = draft_id
        self.errors = errors or []


def sender_first_name(email: NormalizedEmail) -> str:
    """Derive a greeting name from sender display name or email local part."""
    if email.sender_name:
        return email.sender_name.split()[0]
    local = email.sender_email.split("@", 1)[0]
    if "." in local:
        return local.split(".", 1)[0].title()
    return local.title() or "there"


def passes_contact_importance_gate(
    email: NormalizedEmail,
    entity_match: EntityMatchResult,
    catalogs: Catalogs | None = None,
) -> bool:
    """Apply the same contact importance gate as the classifier before rule matching."""
    classifier = RuleBasedClassifier(catalogs or load_catalogs())
    importance = classifier._contact_importance(email.sender_email)
    if importance == "low":
        return False
    if importance == "medium" and not classifier._medium_keyword_match(email, entity_match):
        return False
    return True


def _keywords_match(keywords: list[str], text: str, mode: MatchMode) -> bool:
    if not keywords:
        return False
    normalized = text.lower()
    if mode == "any":
        return any(keyword.lower() in normalized for keyword in keywords)
    return all(keyword.lower() in normalized for keyword in keywords)


def _keyword_in_either(keyword: str, subject: str, body: str) -> bool:
    needle = keyword.lower()
    return needle in subject.lower() or needle in body.lower()


def rule_matches(email: NormalizedEmail, rule: EmailRule) -> bool:
    """Return True when an enabled rule's keyword configuration matches the email."""
    match_cfg = rule.match
    subject = email.subject
    body = email.body_text

    if match_cfg.scope == "subject_only":
        keywords = match_cfg.subject_keywords or match_cfg.body_keywords
        return _keywords_match(keywords, subject, match_cfg.mode)

    if match_cfg.scope == "body_only":
        keywords = match_cfg.body_keywords or match_cfg.subject_keywords
        return _keywords_match(keywords, body, match_cfg.mode)

    if match_cfg.scope == "subject_and_body":
        subject_keywords = match_cfg.subject_keywords
        body_keywords = match_cfg.body_keywords
        if not subject_keywords and not body_keywords:
            return False
        subject_ok = (
            _keywords_match(subject_keywords, subject, match_cfg.mode)
            if subject_keywords
            else True
        )
        body_ok = (
            _keywords_match(body_keywords, body, match_cfg.mode) if body_keywords else True
        )
        if subject_keywords and body_keywords:
            return subject_ok and body_ok
        if subject_keywords:
            return subject_ok
        return body_ok

    keywords = list(dict.fromkeys(match_cfg.subject_keywords + match_cfg.body_keywords))
    if not keywords:
        return False
    if match_cfg.mode == "any":
        return any(_keyword_in_either(keyword, subject, body) for keyword in keywords)
    return all(_keyword_in_either(keyword, subject, body) for keyword in keywords)


def match_rules(
    email: NormalizedEmail,
    catalog: EmailRulesCatalog | None = None,
    rules_path: Path | None = None,
) -> EmailRule | None:
    """Return the first enabled rule that matches the email, in catalog order."""
    rules = (catalog or load_rules(rules_path)).rules
    for rule in rules:
        if rule.enabled and rule_matches(email, rule):
            return rule
    return None


def render_template(
    template: ResponseTemplate,
    *,
    sender_first: str,
    team_name: str,
    ai_response: str = "",
) -> str:
    """Substitute template placeholders for canned or partially filled bodies."""
    rendered = template.body
    rendered = rendered.replace("{sender_first_name}", sender_first)
    rendered = rendered.replace("{team_name}", team_name)
    rendered = rendered.replace("{ai_response}", ai_response)
    return rendered.strip()


def fill_template_with_llm(
    template: ResponseTemplate,
    email: NormalizedEmail,
    llm: OllamaClient | None = None,
) -> str:
    """Fill the {ai_response} section using prompts/template_fill.md."""
    client = llm or OllamaClient()
    prompt_path = PROMPTS_DIR / "template_fill.md"
    prompt_template = prompt_path.read_text(encoding="utf-8")
    sender = email.sender_name or email.sender_email
    replacements = {
        "{template_body}": template.body,
        "{ai_instructions}": template.ai_instructions or "(none)",
        "{email_subject}": email.subject,
        "{email_from}": f"{sender} <{email.sender_email}>".strip(),
        "{email_body}": email.body_text[:4000],
    }
    user_content = prompt_template
    for key, value in replacements.items():
        user_content = user_content.replace(key, value)
    return client.chat_text(messages=[{"role": "user", "content": user_content}])


def build_reply_subject(template: ResponseTemplate, email: NormalizedEmail) -> str:
    """Build the outbound subject line from template prefix and inbound subject."""
    prefix = template.subject_prefix or "Re: "
    if email.subject.lower().startswith(prefix.lower().strip()):
        return email.subject
    return f"{prefix}{email.subject}"


class RuleEngine:
    """Match keyword rules and route matched emails to queue + draft."""

    def __init__(
        self,
        backend: EmailBackend,
        writer: ObsidianWriter | None = None,
        queue_store: ResponseQueueStore | None = None,
        llm: OllamaClient | None = None,
        enabled: bool | None = None,
        catalogs: Catalogs | None = None,
        rules_path: Path | None = None,
        templates_path: Path | None = None,
        team_name: str | None = None,
    ) -> None:
        self.backend = backend
        self.writer = writer
        self.queue_store = queue_store or ResponseQueueStore()
        self.llm = llm
        self._enabled = enabled
        self.catalogs = catalogs
        self.rules_path = rules_path or EMAIL_RULES_FILE
        self.templates_path = templates_path or RESPONSE_TEMPLATES_FILE
        self.team_name = team_name

    @property
    def enabled(self) -> bool:
        return RULE_ENGINE_ENABLED if self._enabled is None else self._enabled

    def _team_name(self) -> str:
        if self.team_name:
            return self.team_name
        return load_team_config().team_name

    def generate_body(
        self,
        rule: EmailRule,
        template: ResponseTemplate,
        email: NormalizedEmail,
    ) -> str:
        """Render a reply body using canned text or LLM fill."""
        first = sender_first_name(email)
        team = self._team_name()
        if rule.generation == "canned":
            return render_template(template, sender_first=first, team_name=team)

        ai_response = fill_template_with_llm(template, email, llm=self.llm)
        return render_template(
            template,
            sender_first=first,
            team_name=team,
            ai_response=ai_response,
        )

    def process_email(
        self,
        email: NormalizedEmail,
        classification: EmailClassification,
        entity_match: EntityMatchResult,
    ) -> RuleEngineResult | None:
        """Run the full rule pipeline when enabled and matched; otherwise None."""
        if not self.enabled:
            return None

        if not passes_contact_importance_gate(email, entity_match, self.catalogs):
            return None

        rule = match_rules(email, rules_path=self.rules_path)
        if rule is None:
            return None

        template = get_template(rule.template_id, self.templates_path)
        if template is None:
            return RuleEngineResult(
                matched=True,
                rule_id=rule.id,
                errors=[f"Template not found: {rule.template_id}"],
            )

        result = RuleEngineResult(matched=True, rule_id=rule.id, template_id=template.id)
        errors: list[str] = []

        try:
            body = self.generate_body(rule, template, email)
            subject = build_reply_subject(template, email)
            result.subject = subject
            result.body = body
        except Exception as exc:
            logger.exception("Rule body generation failed")
            result.errors.append(f"Body generation failed: {exc}")
            return result

        self.queue_store.append_log(
            {
                "message_id": email.message_id,
                "rule_id": rule.id,
                "template_id": template.id,
                "subject": email.subject,
                "sender_email": email.sender_email,
            }
        )

        draft = DraftResponse(
            should_reply=True,
            subject=subject,
            body=body,
            reason=f"Rule engine: {rule.name}",
        )

        thread_note = ""
        if rule.append_to_existing_note and self.writer:
            try:
                thread_note = self.writer.append_to_thread(email, classification, draft)
                result.thread_note = thread_note
            except Exception as exc:
                errors.append(f"Thread note failed: {exc}")
                logger.exception("Thread note append failed")

        draft_id: str | None = None
        try:
            draft_id = self.backend.create_reply_draft(email.message_id, subject, body)
            result.draft_id = draft_id
        except Exception as exc:
            errors.append(f"Draft creation failed: {exc}")
            logger.exception("Rule engine draft creation failed")

        queue_name: QueueName = "approval" if rule.delivery == "approval" else "auto"
        entry = QueueEntry(
            id=self.queue_store.new_entry_id(),
            created_at=self.queue_store.utc_now(),
            message_id=email.message_id,
            rule_id=rule.id,
            template_id=template.id,
            subject=subject,
            body=body,
            status="pending",
            thread_note=thread_note,
            draft_id=draft_id,
        )
        saved = self.queue_store.append_entry(queue_name, entry)
        result.queue_name = queue_name
        result.queue_entry_id = saved.id
        result.errors = errors
        return result
