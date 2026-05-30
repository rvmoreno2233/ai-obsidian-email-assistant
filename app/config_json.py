"""Load and search Creo ETL config.json for client mapping."""

from __future__ import annotations

import json
import re
from functools import lru_cache

from pydantic import BaseModel, Field

from app.config import PROJECT_ROOT

CONFIG_JSON_PATH = PROJECT_ROOT / "config.json"


class ClientSummary(BaseModel):
    """Subset of config.json client fields used for email mapping."""

    client_name: str
    client_abbrev: str = ""
    emr: str = ""
    capture_rx_client_code: str = ""
    wp_client_code: str = ""
    b340_id: str = Field(default="", alias="340b_id")
    verity_abbrev: str = ""
    archive_dir: str = ""

    model_config = {"populate_by_name": True}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", text.lower()) if len(t) >= 3}


@lru_cache(maxsize=1)
def load_clients() -> list[ClientSummary]:
    if not CONFIG_JSON_PATH.exists():
        return []
    data = json.loads(CONFIG_JSON_PATH.read_text(encoding="utf-8"))
    clients: list[ClientSummary] = []
    for raw in data.get("clients", []):
        try:
            clients.append(ClientSummary.model_validate(raw))
        except Exception:
            continue
    return clients


def search_clients(query: str = "", limit: int = 50) -> list[ClientSummary]:
    clients = load_clients()
    if not query:
        return clients[:limit]
    q = query.lower()
    scored: list[tuple[int, ClientSummary]] = []
    for c in clients:
        hay = " ".join(
            filter(
                None,
                [
                    c.client_name,
                    c.client_abbrev,
                    c.b340_id,
                    c.verity_abbrev,
                    c.capture_rx_client_code,
                    c.wp_client_code,
                    c.archive_dir,
                ],
            )
        ).lower()
        if q in hay:
            score = (
                100 if q == c.client_abbrev.lower() else 50 if q in c.client_name.lower() else 10
            )
            scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:limit]]


def get_client_by_abbrev(abbrev: str) -> ClientSummary | None:
    key = abbrev.lower()
    for c in load_clients():
        if c.client_abbrev.lower() == key:
            return c
    return None


def suggest_clients_for_text(text: str, limit: int = 8) -> list[dict]:
    """Score config.json clients against email subject/body/domain text."""
    if not text.strip():
        return []
    text_lower = text.lower()
    text_tokens = _tokens(text)
    results: list[tuple[float, ClientSummary, str]] = []

    for client in load_clients():
        reasons: list[str] = []
        score = 0.0

        abbrev = client.client_abbrev.lower()
        if abbrev and abbrev in text_lower:
            score += 40
            reasons.append(f"abbrev '{client.client_abbrev}'")

        if client.b340_id and client.b340_id.lower() in text_lower:
            score += 35
            reasons.append(f"340B ID {client.b340_id}")

        if client.verity_abbrev and client.verity_abbrev.lower() in text_lower:
            score += 25
            reasons.append(f"Verity {client.verity_abbrev}")

        if client.capture_rx_client_code and client.capture_rx_client_code.lower() in text_lower:
            score += 20
            reasons.append(f"CRx {client.capture_rx_client_code}")

        # Match significant words from client name
        name_parts = _tokens(client.client_name.replace(" d/b/a ", " "))
        overlap = name_parts & text_tokens
        if overlap:
            score += min(30, 5 * len(overlap))
            reasons.append(f"name words: {', '.join(list(overlap)[:3])}")

        if score > 0:
            results.append((score, client, "; ".join(reasons)))

    results.sort(key=lambda x: -x[0])
    return [
        {
            "score": round(score, 1),
            "client_abbrev": client.client_abbrev,
            "client_name": client.client_name,
            "340b_id": client.b340_id,
            "verity_abbrev": client.verity_abbrev,
            "reason": reason,
        }
        for score, client, reason in results[:limit]
    ]
