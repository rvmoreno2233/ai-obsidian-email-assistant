"""Ollama client with Pydantic structured output validation."""

from __future__ import annotations

from typing import Any, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from app.config import ollama_settings

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Base error for LLM operations."""


class LLMConnectionError(LLMError):
    """Cannot reach Ollama server."""


class LLMValidationError(LLMError):
    """Response did not validate against schema."""


class OllamaClient:
    """Thin wrapper around ollama Python SDK."""

    def __init__(
        self,
        host: str | None = None,
        model: str | None = None,
        client=None,
    ) -> None:
        default_host, default_model = ollama_settings()
        self.host = default_host if host is None else host
        self.model = default_model if model is None else model
        self._client = client

    @property
    def client(self):
        if self._client is None:
            try:
                from ollama import Client

                self._client = Client(host=self.host)
            except Exception as e:
                raise LLMConnectionError(f"Failed to create Ollama client: {e}") from e
        return self._client

    def chat_structured(
        self,
        messages: list[dict[str, str]],
        schema_model: type[T],
        temperature: float = 0,
    ) -> T:
        try:
            response = self.client.chat(
                model=self.model,
                messages=messages,
                format=schema_model.model_json_schema(),
                options={"temperature": temperature},
            )
            content = response.message.content
            return schema_model.model_validate_json(content)
        except ValidationError as e:
            raise LLMValidationError(str(e)) from e
        except LLMError:
            raise
        except Exception as e:
            raise LLMConnectionError(str(e)) from e

    def health_check(self, timeout: float = 3.0) -> dict[str, Any]:
        """Probe Ollama /api/tags; return ok flag and available models."""
        result: dict[str, Any] = {
            "ok": False,
            "model": self.model,
            "host": self.host,
            "models_available": [],
        }
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=timeout)
            response.raise_for_status()
            models = response.json().get("models", [])
            result["models_available"] = [m.get("name", "") for m in models if m.get("name")]
            result["ok"] = True
            result["model_ready"] = any(
                name == self.model or name.split(":")[0] == self.model.split(":")[0]
                for name in result["models_available"]
            )
        except (requests.RequestException, ValueError):
            result["model_ready"] = False
        return result

    def chat_text(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
    ) -> str:
        """Unstructured chat for template assist/fill (no JSON schema)."""
        try:
            response = self.client.chat(
                model=self.model,
                messages=messages,
                options={"temperature": temperature},
            )
            content = response.message.content
            return (content or "").strip()
        except LLMError:
            raise
        except Exception as e:
            raise LLMConnectionError(str(e)) from e
