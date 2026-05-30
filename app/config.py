"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = PROJECT_ROOT / "prompts"
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))


def reload_env() -> None:
    """Re-read .env so Studio picks up OLLAMA_MODEL changes without a full restart."""
    load_dotenv(override=True)


def ollama_settings() -> tuple[str, str]:
    """Current Ollama host and model from environment."""
    reload_env()
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3.1")
    return host, model


MSGRAPH_CLIENT_ID = os.getenv("MSGRAPH_CLIENT_ID", "")
MSGRAPH_TENANT_ID = os.getenv("MSGRAPH_TENANT_ID", "common")
_MSAL_RESERVED = frozenset({"openid", "profile", "offline_access"})
_GRAPH_SCOPE_PREFIX = "https://graph.microsoft.com/"


def _parse_graph_scopes(raw: str) -> list[str]:
    """Normalize Graph delegated scopes for MSAL (reserved scopes omitted)."""
    scopes: list[str] = []
    for part in raw.split():
        token = part.strip()
        if not token or token.lower() in _MSAL_RESERVED:
            continue
        if token.startswith("https://"):
            scopes.append(token)
        else:
            scopes.append(f"{_GRAPH_SCOPE_PREFIX}{token}")
    return scopes or [
        f"{_GRAPH_SCOPE_PREFIX}Mail.Read",
        f"{_GRAPH_SCOPE_PREFIX}Mail.ReadWrite",
    ]


MSGRAPH_SCOPES = _parse_graph_scopes(
    os.getenv("MSGRAPH_SCOPES", "Mail.Read Mail.ReadWrite"),
)

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "mock").lower()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
CLASSIFIER_MODE = os.getenv("CLASSIFIER_MODE", "rule").lower()
RESPONDER_MODE = os.getenv("RESPONDER_MODE", "rule").lower()

VAULT_DIR = PROJECT_ROOT / "vault"
_default_vault = str(VAULT_DIR) if VAULT_DIR.is_dir() else ""
OBSIDIAN_VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH", _default_vault)
MSAL_CACHE_PATH = Path.home() / ".cache" / "email-assistant" / "msal_cache.json"


class AutoSendMode(StrEnum):
    OFF = "off"
    SAFE = "safe"
    FULL = "full"


AUTO_SEND_MODE = AutoSendMode(os.getenv("AUTO_SEND_MODE", "off").lower())
UPDATE_WAITING_YAML = os.getenv("UPDATE_WAITING_YAML", "false").lower() in (
    "1",
    "true",
    "yes",
)

RULE_ENGINE_ENABLED = os.getenv("RULE_ENGINE_ENABLED", "false").lower() in (
    "1",
    "true",
    "yes",
)
POLLER_INTERVAL_SECONDS = int(os.getenv("POLLER_INTERVAL_SECONDS", "300"))
QUEUE_DIR = Path(os.getenv("QUEUE_DIR", str(DATA_DIR / "queue")))

NEWSLETTER_DOMAINS = frozenset(
    {
        "mailchimp.com",
        "sendgrid.net",
        "constantcontact.com",
        "substack.com",
        "beehiiv.com",
        "linkedin.com",
        "noreply",
        "no-reply",
    }
)
