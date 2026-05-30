"""Tests for OllamaClient health check and unstructured chat."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.llm_client import LLMConnectionError, OllamaClient


def test_health_check_ok():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "models": [{"name": "llama3.1:latest"}, {"name": "mistral:latest"}],
    }

    with patch("app.llm_client.requests.get", return_value=mock_response) as mock_get:
        client = OllamaClient(host="http://127.0.0.1:11434", model="llama3.1")
        result = client.health_check(timeout=5)

    mock_get.assert_called_once_with("http://127.0.0.1:11434/api/tags", timeout=5)
    assert result == {
        "ok": True,
        "model": "llama3.1",
        "host": "http://127.0.0.1:11434",
        "models_available": ["llama3.1:latest", "mistral:latest"],
        "model_ready": True,
    }


def test_health_check_unreachable():
    with patch(
        "app.llm_client.requests.get",
        side_effect=requests.ConnectionError("connection refused"),
    ):
        client = OllamaClient(host="http://127.0.0.1:11434", model="llama3.1")
        result = client.health_check()

    assert result["ok"] is False
    assert result["model"] == "llama3.1"
    assert result["host"] == "http://127.0.0.1:11434"
    assert result["models_available"] == []
    assert result["model_ready"] is False


def test_health_check_http_error():
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.HTTPError("503")

    with patch("app.llm_client.requests.get", return_value=mock_response):
        result = OllamaClient().health_check()

    assert result["ok"] is False
    assert result["models_available"] == []
    assert result["model_ready"] is False


def test_chat_text_returns_stripped_response():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.message.content = "  Hello from Ollama.\n"
    mock_client.chat.return_value = mock_response

    client = OllamaClient(client=mock_client)
    text = client.chat_text(messages=[{"role": "user", "content": "Say hello"}])

    assert text == "Hello from Ollama."
    mock_client.chat.assert_called_once_with(
        model=client.model,
        messages=[{"role": "user", "content": "Say hello"}],
        options={"temperature": 0.3},
    )


def test_chat_text_empty_content():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.message.content = None
    mock_client.chat.return_value = mock_response

    client = OllamaClient(client=mock_client)
    assert client.chat_text(messages=[{"role": "user", "content": "test"}]) == ""


def test_chat_text_connection_error():
    mock_client = MagicMock()
    mock_client.chat.side_effect = RuntimeError("timeout")

    client = OllamaClient(client=mock_client)
    with pytest.raises(LLMConnectionError, match="timeout"):
        client.chat_text(messages=[{"role": "user", "content": "test"}])


def test_template_prompt_files_exist():
    from app.config import PROMPTS_DIR

    assist = (PROMPTS_DIR / "template_assist.md").read_text(encoding="utf-8")
    fill = (PROMPTS_DIR / "template_fill.md").read_text(encoding="utf-8")

    assert "{description}" in assist
    assert "{team_name}" in assist
    assert "{sender_first_name}" in assist
    assert "{ai_response}" in assist

    assert "{template_body}" in fill
    assert "{ai_instructions}" in fill
    assert "{email_subject}" in fill
    assert "{email_from}" in fill
    assert "{email_body}" in fill
