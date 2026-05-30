"""Draft reply generation: rule-based templates and optional LLM."""

from __future__ import annotations

from app.config import PROMPTS_DIR, RESPONDER_MODE
from app.schemas import DraftResponse, EmailClassification, NormalizedEmail


class RuleBasedResponder:
    """Template-based draft replies for MVP."""

    def draft(
        self,
        email: NormalizedEmail,
        classification: EmailClassification,
    ) -> DraftResponse:
        reply_categories = ("needs_response", "meeting_request", "waiting_info_arrived")
        if classification.category not in reply_categories:
            return DraftResponse(
                should_reply=False,
                reason=f"No reply needed for category: {classification.category}",
            )

        subject = email.subject
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        body = (
            f"Hi {email.sender_name or 'there'},\n\n"
            "Thanks for your email. I've received this and will review and follow up shortly.\n\n"
            "Best regards"
        )
        return DraftResponse(
            should_reply=True,
            auto_send_allowed=False,
            subject=subject,
            body=body,
            reason="Rule-based acknowledgment for needs_response",
        )


def _load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


class LLMResponder:
    """LLM-backed draft responder with safety overrides."""

    def __init__(self, rule_fallback: RuleBasedResponder | None = None, llm=None) -> None:
        self.rule_fallback = rule_fallback or RuleBasedResponder()
        self._llm = llm

    @property
    def llm(self):
        if self._llm is None:
            from app.llm_client import OllamaClient

            self._llm = OllamaClient()
        return self._llm

    def draft(
        self,
        email: NormalizedEmail,
        classification: EmailClassification,
    ) -> DraftResponse:
        if classification.category in ("newsletter", "ignore_low_priority", "fyi"):
            return DraftResponse(
                should_reply=False,
                reason=f"No reply for category {classification.category}",
            )
        try:
            prompt_template = _load_prompt("draft_reply.md")
            user_content = f"""{prompt_template}

## Original email
Subject: {email.subject}
From: {email.sender_email}
Body:
{email.body_text[:3000]}

## Classification
Category: {classification.category}
Priority: {classification.priority}
Summary: {classification.summary}
"""
            result = self.llm.chat_structured(
                messages=[{"role": "user", "content": user_content}],
                schema_model=DraftResponse,
                temperature=0.3,
            )
            return result.model_copy(update={"auto_send_allowed": False})
        except Exception:
            fallback = self.rule_fallback.draft(email, classification)
            return fallback.model_copy(update={"reason": f"LLM fallback: {fallback.reason}"})


def get_responder(mode: str | None = None) -> RuleBasedResponder | LLMResponder:
    m = (mode or RESPONDER_MODE).lower()
    if m == "llm":
        return LLMResponder()
    return RuleBasedResponder()


def draft_response(
    email: NormalizedEmail,
    classification: EmailClassification,
    responder: RuleBasedResponder | LLMResponder | None = None,
) -> DraftResponse:
    r = responder or get_responder()
    return r.draft(email, classification)
