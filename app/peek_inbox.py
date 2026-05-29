"""Fetch recent inbox messages and report pipeline readiness gaps."""

from __future__ import annotations

import html
import os
import re
import sys
from dataclasses import dataclass, field

from app.config import DATA_DIR, MSGRAPH_CLIENT_ID, MSGRAPH_TENANT_ID
from app.entity_matcher import load_catalogs, match_entities
from app.graph_client import MsGraphBackend
from app.schemas import NormalizedEmail


@dataclass
class EmailGapReport:
    email: NormalizedEmail
    body_is_html: bool = False
    body_plain_preview: str = ""
    entity_company: str | None = None
    entity_contact: str | None = None
    entity_projects: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _strip_html(text: str) -> str:
    if not text:
        return ""
    # Rough strip for preview — full HTML→text is a known gap
    no_tags = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", text, flags=re.I | re.S)
    no_tags = re.sub(r"<[^>]+>", " ", no_tags)
    return html.unescape(re.sub(r"\s+", " ", no_tags)).strip()


def _looks_like_html(text: str) -> bool:
    return bool(text and re.search(r"<(html|body|div|p|table|span)\b", text, re.I))


def check_prerequisites() -> list[str]:
    """Return blocking issues before calling Graph."""
    gaps: list[str] = []
    if not MSGRAPH_CLIENT_ID:
        gaps.append(
            "MSGRAPH_CLIENT_ID is not set — copy .env.example to .env and add your "
            "Azure app registration client ID"
        )
    return gaps


def analyze_email(email: NormalizedEmail) -> EmailGapReport:
    catalogs = load_catalogs(DATA_DIR)
    entities = match_entities(email, catalogs)
    report = EmailGapReport(
        email=email,
        entity_company=entities.company,
        entity_contact=entities.contact,
        entity_projects=entities.projects,
    )

    body = email.body_text or ""
    report.body_is_html = _looks_like_html(body)
    report.body_plain_preview = _strip_html(body)[:200]

    if not email.sender_email:
        report.gaps.append("Missing sender email — entity matching will fail")
    if not email.subject:
        report.warnings.append("Empty subject — classification harder")
    if not body.strip():
        report.gaps.append("Empty body — cannot classify content or match waiting-for keywords")
    elif report.body_is_html:
        report.warnings.append(
            "Body is HTML — classifier/keyword rules run on raw HTML (strip HTML before classify)"
        )
    if not entities.company:
        domain = email.sender_email.split("@")[-1] if "@" in email.sender_email else "?"
        report.gaps.append(
            f"No company match for sender domain '{domain}' — add to data/companies.yaml"
        )
    if not entities.contact:
        report.warnings.append(
            f"Sender '{email.sender_email}' not in data/contacts.yaml — contact note won't update"
        )
    if not entities.projects:
        report.warnings.append("No project keyword match — project notes won't update")

    return report


def peek_inbox(top: int = 5) -> int:
    """Fetch and print gap analysis for recent inbox messages."""
    prereq = check_prerequisites()
    if prereq:
        print("BLOCKERS (fix before Graph will work):\n")
        for g in prereq:
            print(f"  ✗ {g}")
        print("\nSetup steps:")
        print("  1. Azure Portal → App registrations → your app → copy Client ID")
        print("  2. cp .env.example .env  →  set MSGRAPH_CLIENT_ID=...")
        print("  3. email-assistant authenticate")
        print("  4. email-assistant peek")
        return 1

    print(f"Connecting to Microsoft Graph (tenant: {MSGRAPH_TENANT_ID})...")
    print(f"Fetching last {top} inbox messages...\n")

    try:
        backend = MsGraphBackend()
        emails = backend.list_recent_messages(top=top)
    except Exception as e:
        import traceback

        print(f"GRAPH ERROR: {e}\n")
        if os.getenv("PEEK_DEBUG"):
            traceback.print_exc()
        print("Common fixes:")
        print("  • Run: email-assistant authenticate")
        print("  • App permissions: Mail.Read, Mail.ReadWrite, offline_access")
        print("  • Enable public client flows on the app registration")
        return 1

    if not emails:
        print("No messages returned (empty inbox or permission issue).")
        return 0

    all_gaps: set[str] = set()
    all_warnings: set[str] = set()
    unknown_domains: set[str] = set()
    unmatched_senders: set[str] = set()

    for i, email in enumerate(emails, 1):
        report = analyze_email(email)
        all_gaps.update(report.gaps)
        all_warnings.update(report.warnings)
        if not report.entity_company and "@" in email.sender_email:
            unknown_domains.add(email.sender_email.split("@", 1)[1].lower())
        if not report.entity_contact:
            unmatched_senders.add(email.sender_email.lower())

        print("=" * 72)
        print(f"#{i}  {email.subject[:60]}")
        print(f"    From:     {report.entity_contact or email.sender_name or '?'} "
              f"<{email.sender_email}>")
        print(f"    Received: {email.received_at}")
        print(f"    ID:       {email.message_id[:50]}...")
        print(f"    Company:  {report.entity_company or '— NO MATCH —'}")
        print(f"    Projects: {', '.join(report.entity_projects) or '— none —'}")
        if report.body_plain_preview:
            print(f"    Preview:  {report.body_plain_preview[:120]}...")
        if report.gaps:
            for g in report.gaps:
                print(f"    GAP:      {g}")
        if report.warnings:
            for w in report.warnings:
                print(f"    WARN:     {w}")
        print()

    print("=" * 72)
    print("SUMMARY — gaps before running the full agent\n")

    print(f"Messages fetched:     {len(emails)}")
    print(f"Unknown domains:      {len(unknown_domains)}")
    for d in sorted(unknown_domains):
        print(f"  • {d}")
    print(f"Unmatched contacts:   {len(unmatched_senders)}")
    for s in sorted(unmatched_senders)[:10]:
        print(f"  • {s}")
    if len(unmatched_senders) > 10:
        print(f"  ... and {len(unmatched_senders) - 10} more")

    print("\nUnique issues across this batch:")
    if all_gaps:
        for g in sorted(all_gaps):
            print(f"  ✗ {g}")
    else:
        print("  ✓ No hard gaps on fetched messages")

    if all_warnings:
        print("\nWarnings (agent works but quality may suffer):")
        for w in sorted(all_warnings):
            print(f"  ! {w}")

    print("\nRecommended next steps:")
    if unknown_domains:
        print("  1. Add unknown domains to data/companies.yaml")
    if unmatched_senders:
        print("  2. Add frequent senders to data/contacts.yaml")
    if any(_looks_like_html(e.body_text) for e in emails):
        print("  3. Add HTML→plain-text stripping in graph_client before classification")
    print("  4. Run full pipeline: EMAIL_BACKEND=graph python run_local.py")

    return 0


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    raise SystemExit(peek_inbox(top=n))
