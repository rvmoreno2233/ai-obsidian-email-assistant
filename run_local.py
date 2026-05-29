#!/usr/bin/env python3
"""Local orchestration entrypoint for email assistant."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from app.action_router import ActionRouter
from app.classifier import classify_email, get_classifier
from app.config import OBSIDIAN_VAULT_PATH
from app.entity_matcher import match_entities
from app.graph_client import get_email_backend
from app.ingestion import load_recent_emails
from app.obsidian_writer import ObsidianWriter
from app.responder import draft_response, get_responder

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    backend = get_email_backend()
    emails = load_recent_emails(backend)

    writer = None
    if OBSIDIAN_VAULT_PATH:
        vault = Path(OBSIDIAN_VAULT_PATH)
        vault.mkdir(parents=True, exist_ok=True)
        writer = ObsidianWriter(vault)
    else:
        logger.warning("OBSIDIAN_VAULT_PATH not set — skipping Obsidian writes")

    classifier = get_classifier()
    responder = get_responder()
    router = ActionRouter(writer=writer, backend=backend)

    print(f"\nProcessing {len(emails)} email(s)...\n")
    print(f"{'Subject':<45} {'Category':<22} {'Priority':<8} {'Draft'}")
    print("-" * 90)

    for email in emails:
        entity_match = match_entities(email)
        classification = classify_email(email, entity_match, classifier)
        response = draft_response(email, classification, responder)
        action = router.route(email, classification, response)

        draft_flag = "yes" if response.should_reply else "no"
        print(
            f"{email.subject[:43]:<45} "
            f"{classification.category:<22} "
            f"{classification.priority:<8} "
            f"{draft_flag}"
        )

        if classification.category == "waiting_info_arrived":
            print(f"  >> Important info arrived: {email.subject}")

        if response.should_reply:
            print(f"  >> Draft needed: {email.subject}")

        if action.errors:
            for err in action.errors:
                print(f"  !! {err}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
