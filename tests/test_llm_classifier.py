"""Tests for LLM classifier/responder with mocked Ollama."""

import json
from unittest.mock import MagicMock

import pytest

from app.classifier import LLMClassifier, RuleBasedClassifier
from app.config import DATA_DIR, FIXTURES_DIR
from app.entity_matcher import load_catalogs, match_entities
from app.llm_client import LLMValidationError, OllamaClient
from app.responder import LLMResponder
from app.schemas import DraftResponse, EmailClassification, NormalizedEmail


@pytest.fixture
def schema_email() -> NormalizedEmail:
    raw = json.loads((FIXTURES_DIR / "sample_emails.json").read_text())
    return NormalizedEmail.model_validate(
        next(e for e in raw if e["message_id"] == "msg-needs-response")
    )


def test_ollama_client_structured_mock(schema_email):
    mock_client = MagicMock()
    classification_json = EmailClassification(
        category="needs_response",
        priority="high",
        confidence=0.9,
        summary="Test",
        reason="Test",
    ).model_dump_json()

    mock_response = MagicMock()
    mock_response.message.content = classification_json
    mock_client.chat.return_value = mock_response

    ollama = OllamaClient(client=mock_client)
    result = ollama.chat_structured(
        messages=[{"role": "user", "content": "test"}],
        schema_model=EmailClassification,
    )
    assert result.category == "needs_response"


def test_llm_classifier_fallback_on_error(schema_email):
    catalogs = load_catalogs(DATA_DIR)
    rule = RuleBasedClassifier(catalogs)
    mock_llm = MagicMock()
    mock_llm.chat_structured.side_effect = LLMValidationError("bad json")

    clf = LLMClassifier(rule_fallback=rule, llm=mock_llm)
    entities = match_entities(schema_email, catalogs)
    result = clf.classify(schema_email, entities)
    assert result.needs_human_review is True
    assert "fallback" in result.reason.lower() or result.category == "needs_response"


def test_llm_responder_forces_auto_send_false(schema_email):
    catalogs = load_catalogs(DATA_DIR)
    rule = RuleBasedClassifier(catalogs)
    entities = match_entities(schema_email, catalogs)
    classification = rule.classify(schema_email, entities)

    draft_json = DraftResponse(
        should_reply=True,
        auto_send_allowed=True,
        subject="Re: test",
        body="Hello",
        reason="test",
    ).model_dump_json()

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.message.content = draft_json
    mock_client.chat.return_value = mock_response

    ollama = OllamaClient(client=mock_client)
    responder = LLMResponder(llm=ollama)
    result = responder.draft(schema_email, classification)
    assert result.auto_send_allowed is False
