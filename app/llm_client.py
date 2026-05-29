"""Ollama client with Pydantic structured output validation."""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import OLLAMA_HOST, OLLAMA_MODEL

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
        self.host = host or OLLAMA_HOST
        self.model = model or OLLAMA_MODEL
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
