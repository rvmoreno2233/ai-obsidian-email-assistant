"""Email ingestion from configured backend."""

from __future__ import annotations

from app.graph_client import EmailBackend, get_email_backend
from app.schemas import NormalizedEmail


def load_recent_emails(
    backend: EmailBackend | None = None,
    top: int = 25,
) -> list[NormalizedEmail]:
    """Pull recent messages from the email backend."""
    be = backend or get_email_backend()
    return be.list_recent_messages(top=top)
