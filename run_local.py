#!/usr/bin/env python3
"""Local orchestration entrypoint for email assistant."""

from __future__ import annotations

import logging
import sys

from app.config import RULE_ENGINE_ENABLED
from app.inbox_processor import process_inbox

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    if RULE_ENGINE_ENABLED:
        logger.info("Rule engine enabled — matched emails route to queue + draft")

    result = process_inbox()

    print(f"\nProcessing {result.processed} email(s)...\n")
    print(f"{'Subject':<45} {'Category':<22} {'Priority':<8} {'Draft':<5} Rule")
    print("-" * 90)

    for summary in result.emails:
        draft_flag = "yes" if summary.draft_created else "no"
        rule_flag = summary.rule_id or "-"
        print(
            f"{summary.subject[:43]:<45} "
            f"{summary.category:<22} "
            f"{summary.priority:<8} "
            f"{draft_flag:<5} {rule_flag}"
        )

        if summary.category == "waiting_info_arrived":
            print(f"  >> Important info arrived: {summary.subject}")

        if summary.draft_created:
            print(f"  >> Draft created: {summary.subject}")

        if summary.errors:
            for err in summary.errors:
                print(f"  !! {err}")

    if result.errors:
        for err in result.errors:
            print(f"!! {err}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
