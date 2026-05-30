"""Email classification: rule-based and optional LLM-backed."""

from __future__ import annotations

from app.config import CLASSIFIER_MODE, PROMPTS_DIR
from app.entity_matcher import Catalogs, is_newsletter_sender, load_catalogs
from app.schemas import EmailClassification, EntityMatchResult, NormalizedEmail


class RuleBasedClassifier:
    """Deterministic classifier using entity matches and heuristics."""

    def __init__(self, catalogs: Catalogs | None = None) -> None:
        self.catalogs = catalogs or load_catalogs()

    def _contact_importance(self, sender_email: str) -> str | None:
        sender = sender_email.lower()
        for c in self.catalogs.contacts.contacts:
            if c.email.lower() == sender:
                return c.importance
        return None

    def _medium_keyword_match(
        self, email: NormalizedEmail, entity_match: EntityMatchResult
    ) -> bool:
        blob = f"{email.subject} {email.body_text}".lower()
        if "?" in email.subject or "?" in email.body_text:
            return True
        if any(w.matched for w in entity_match.waiting_matches):
            return True
        for p in entity_match.projects:
            for proj in self.catalogs.projects.projects:
                if proj.name == p:
                    for kw in proj.keywords:
                        if kw.lower() in blob:
                            return True
        if entity_match.company:
            for co in self.catalogs.companies.companies:
                if co.name == entity_match.company:
                    for kw in co.keywords:
                        if kw.lower() in blob:
                            return True
        triggers = (
            "can you",
            "please confirm",
            "when will",
            "deadline",
            "action required",
            "urgent",
            "blocker",
            "approval",
        )
        return any(k in blob for k in triggers)

    def classify(
        self,
        email: NormalizedEmail,
        entity_match: EntityMatchResult,
    ) -> EmailClassification:
        company = entity_match.company
        contact = entity_match.contact
        project = entity_match.projects[0] if entity_match.projects else None
        blob = f"{email.subject} {email.body_text}".lower()
        keywords: list[str] = []

        sender_importance = self._contact_importance(email.sender_email)
        if sender_importance == "low":
            return EmailClassification(
                category="ignore_low_priority",
                priority="low",
                confidence=0.95,
                company=company,
                contact=contact,
                project=project,
                keywords=["ignored"],
                summary="Contact marked low importance (ignore)",
                reason="Contact importance is Low — ignore",
                needs_human_review=False,
            )
        if sender_importance == "medium" and not self._medium_keyword_match(email, entity_match):
            return EmailClassification(
                category="ignore_low_priority",
                priority="low",
                confidence=0.7,
                company=company,
                contact=contact,
                project=project,
                keywords=["keyword-filter"],
                summary="No keyword match for medium-importance contact",
                reason="Medium importance — keyword filtered (no match)",
                needs_human_review=False,
            )

        # Waiting info arrived
        waiting_hits = [w for w in entity_match.waiting_matches if w.matched]
        if waiting_hits:
            w = waiting_hits[0]
            return EmailClassification(
                category="waiting_info_arrived",
                priority="high",
                confidence=0.9,
                company=company,
                contact=contact,
                project=project or w.project,
                keywords=[w.waiting_item_id],
                summary=f"Information may have arrived for waiting item: {w.waiting_item_id}",
                reason=f"Matched waiting keywords: {w.evidence}",
                needs_human_review=True,
            )

        # Newsletter / marketing
        if is_newsletter_sender(email):
            return EmailClassification(
                category="newsletter",
                priority="low",
                confidence=0.85,
                company=company,
                contact=contact,
                project=project,
                keywords=["newsletter"],
                summary="Likely newsletter or marketing email",
                reason="Sender domain or unsubscribe/marketing signals",
                needs_human_review=False,
            )

        # Invoice / admin
        if any(k in blob for k in ("invoice", "receipt", "billing", "payment due")):
            return EmailClassification(
                category="invoice_or_admin",
                priority="medium",
                confidence=0.8,
                company=company,
                contact=contact,
                project=project,
                keywords=["invoice"],
                summary="Administrative or billing email",
                reason="Billing/invoice keywords in body",
                needs_human_review=True,
            )

        # Meeting request
        if any(
            k in blob
            for k in ("meeting", "calendar invite", "teams meeting", "zoom", "schedule a call")
        ):
            return EmailClassification(
                category="meeting_request",
                priority="medium",
                confidence=0.75,
                company=company,
                contact=contact,
                project=project,
                keywords=["meeting"],
                summary="Meeting or calendar-related email",
                reason="Meeting/scheduling keywords",
                needs_human_review=True,
            )

        # Needs response (before project_update so questions take priority)
        contact_importance = "medium"
        if contact:
            for c in self.catalogs.contacts.contacts:
                if c.name == contact:
                    contact_importance = c.importance
                    break

        has_question = "?" in email.body_text or "?" in email.subject
        if has_question or (
            contact_importance == "high"
            and any(k in blob for k in ("can you", "please confirm", "when will", "deadline"))
        ):
            priority = "high" if contact_importance == "high" else "medium"
            return EmailClassification(
                category="needs_response",
                priority=priority,
                confidence=0.75,
                company=company,
                contact=contact,
                project=project,
                keywords=["question"] if has_question else [],
                summary="Email likely requires a reply",
                reason="Direct question or high-importance contact",
                needs_human_review=True,
            )

        # Project update
        project_kws = []
        for p in self.catalogs.projects.projects:
            if project and p.name == project:
                for kw in p.keywords:
                    if kw.lower() in blob:
                        project_kws.append(kw)
        if project_kws or (
            project and any(k in blob for k in ("update", "status", "progress", "deploy"))
        ):
            return EmailClassification(
                category="project_update",
                priority="medium",
                confidence=0.7,
                company=company,
                contact=contact,
                project=project,
                keywords=project_kws[:5],
                summary="Project-related update",
                reason="Project keywords or update language",
                needs_human_review=True,
            )

        # Low priority ignore hints
        if any(k in blob for k in ("out of office", "automatic reply", "auto-reply")):
            return EmailClassification(
                category="ignore_low_priority",
                priority="low",
                confidence=0.8,
                company=company,
                contact=contact,
                project=project,
                keywords=["auto-reply"],
                summary="Automated or out-of-office message",
                reason="Auto-reply detected",
                needs_human_review=False,
            )

        return EmailClassification(
            category="fyi",
            priority="low",
            confidence=0.6,
            company=company,
            contact=contact,
            project=project,
            keywords=keywords,
            summary="Informational email",
            reason="No higher-priority signals matched",
            needs_human_review=False,
        )


def _load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


class LLMClassifier:
    """LLM-backed classifier with rule-based fallback."""

    def __init__(
        self,
        rule_fallback: RuleBasedClassifier | None = None,
        llm=None,
    ) -> None:
        self.rule_fallback = rule_fallback or RuleBasedClassifier()
        self._llm = llm

    @property
    def llm(self):
        if self._llm is None:
            from app.llm_client import OllamaClient

            self._llm = OllamaClient()
        return self._llm

    def classify(
        self,
        email: NormalizedEmail,
        entity_match: EntityMatchResult,
    ) -> EmailClassification:
        from app.entity_matcher import get_open_waiting_items

        rule_result = self.rule_fallback.classify(email, entity_match)
        try:
            prompt_template = _load_prompt("classify_email.md")
            waiting_items = get_open_waiting_items(self.rule_fallback.catalogs)
            user_content = f"""{prompt_template}

## Email
Subject: {email.subject}
From: {email.sender_name or ''} <{email.sender_email}>
Received: {email.received_at}
Body:
{email.body_text[:4000]}

## Candidate matches
Company: {entity_match.company}
Contact: {entity_match.contact}
Projects: {', '.join(entity_match.projects)}
Open waiting items: {[w.id for w in waiting_items]}
"""
            result = self.llm.chat_structured(
                messages=[{"role": "user", "content": user_content}],
                schema_model=EmailClassification,
                temperature=0,
            )
            if result.confidence < 0.85:
                result = result.model_copy(update={"needs_human_review": True})
            return result
        except Exception:
            return rule_result.model_copy(
                update={
                    "needs_human_review": True,
                    "reason": f"LLM fallback: {rule_result.reason}",
                }
            )


def get_classifier(mode: str | None = None) -> RuleBasedClassifier | LLMClassifier:
    m = (mode or CLASSIFIER_MODE).lower()
    if m == "llm":
        return LLMClassifier()
    return RuleBasedClassifier()


def classify_email(
    email: NormalizedEmail,
    entity_match: EntityMatchResult,
    classifier: RuleBasedClassifier | LLMClassifier | None = None,
) -> EmailClassification:
    clf = classifier or get_classifier()
    return clf.classify(email, entity_match)
