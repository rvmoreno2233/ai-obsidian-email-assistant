#!/usr/bin/env python3
"""Local orchestration entrypoint for email assistant."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from app.action_router import ActionRouter
from app.classifier import classify_email, get_classifier
from app.config import OBSIDIAN_VAULT_PATH, RULE_ENGINE_ENABLED
from app.entity_matcher import match_entities
from app.graph_client import get_email_backend
from app.ingestion import load_recent_emails
from app.obsidian_writer import ObsidianWriter
from app.responder import draft_response, get_responder
from app.rule_engine import RuleEngine

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
    rule_engine = RuleEngine(backend=backend, writer=writer) if RULE_ENGINE_ENABLED else None
    router = ActionRouter(writer=writer, backend=backend, rule_engine=rule_engine)

    if RULE_ENGINE_ENABLED:
        logger.info("Rule engine enabled — matched emails route to queue + draft")

    print(f"\nProcessing {len(emails)} email(s)...\n")
    print(f"{'Subject':<45} {'Category':<22} {'Priority':<8} {'Draft':<5} Rule")
    print("-" * 90)

    for email in emails:
        entity_match = match_entities(email)
        classification = classify_email(email, entity_match, classifier)
        response = draft_response(email, classification, responder)
        action = router.route(email, classification, response, entity_match=entity_match)

        draft_flag = "yes" if action.draft_created or response.should_reply else "no"
        rule_flag = action.rule_id or "-"
        print(
            f"{email.subject[:43]:<45} "
            f"{classification.category:<22} "
            f"{classification.priority:<8} "
            f"{draft_flag:<5} {rule_flag}"
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
