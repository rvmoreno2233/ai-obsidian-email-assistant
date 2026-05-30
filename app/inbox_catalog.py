"""Discover domains and contacts from inbox history for agent setup."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

import yaml

from app.config import DATA_DIR
from app.graph_client import MsGraphBackend

CATALOG_DIR = DATA_DIR / "catalog"
DOMAINS_FILE = CATALOG_DIR / "inbox_domains.yaml"
CONTACTS_FILE = CATALOG_DIR / "inbox_contacts.yaml"
CATEGORIES_FILE = DATA_DIR / "domain_categories.yaml"

# User-provided seed categories (domain substring → category)
DEFAULT_DOMAIN_HINTS: dict[str, str] = {
    "capturerx.com": "340b_vendor",
    "verity340b.com": "340b_vendor",
    "i340b.com": "340b_vendor",
    "cervey.com": "340b_vendor",
    "creocomp.com": "internal",
    "cardinalhealth.com": "wholesaler",
    "cardinal.com": "wholesaler",
}

CATEGORY_LABELS = {
    "340b_vendor": "340B vendor",
    "pharmacy": "Pharmacy",
    "wholesaler": "Wholesaler",
    "internal": "Internal (Creo)",
    "client": "Client",
    "partner": "Partner",
    "newsletter": "Newsletter / marketing",
    "personal": "Personal",
    "ignore": "Ignore / low priority",
    "unassigned": "Unassigned — you categorize",
}

# Hidden by default in Studio domain/contact lists; re-categorize to include
DEFAULT_EXCLUDED_CATEGORIES = frozenset({"ignore", "newsletter"})

# Per-contact importance within an included domain (Studio Contacts tab)
CONTACT_IMPORTANCE_LABELS = {
    "high": "High — always on",
    "medium": "Medium — keyword filtered",
    "low": "Low — ignore",
}


@dataclass
class MessageMeta:
    message_id: str
    subject: str
    sender_email: str
    sender_name: str | None
    received_at: str
    body_preview: str = ""


@dataclass
class SampleEmail:
    message_id: str
    subject: str
    sender_email: str
    sender_name: str | None = None
    received_at: str = ""
    body_preview: str = ""


@dataclass
class DomainStats:
    domain: str
    message_count: int = 0
    contact_count: int = 0
    first_seen: str = ""
    last_seen: str = ""
    sample_subjects: list[str] = field(default_factory=list)
    sample_emails: list[SampleEmail] = field(default_factory=list)
    contacts: list[str] = field(default_factory=list)
    suggested_category: str = "unassigned"
    category: str = "unassigned"
    company: str | None = None
    config_client_abbrev: str | None = None
    config_client_name: str | None = None


@dataclass
class ContactStats:
    email: str
    name: str | None
    domain: str
    message_count: int = 0
    first_seen: str = ""
    last_seen: str = ""
    sample_subjects: list[str] = field(default_factory=list)
    rank_score: float = 0.0
    importance: str = "medium"  # high | medium | low
    agent_enabled: bool = False
    company: str | None = None
    category: str = "unassigned"


def extract_domain(email: str) -> str:
    if "@" not in email:
        return ""
    return email.split("@", 1)[1].lower().strip()


def suggest_category(domain: str, hints: dict[str, str] | None = None) -> str:
    hints = hints or DEFAULT_DOMAIN_HINTS
    d = domain.lower()
    for pattern, cat in hints.items():
        if pattern in d or d.endswith(pattern):
            return cat
    if any(x in d for x in ("noreply", "no-reply", "donotreply", "notifications")):
        return "newsletter"
    return "unassigned"


def suggest_company_name(domain: str, category: str) -> str:
    """Human-readable company name from domain."""
    known = {
        "capturerx.com": "CaptureRx",
        "verity340b.com": "Verity 340B",
        "i340b.com": "Verity 340B",
        "creocomp.com": "Creo",
        "cardinalhealth.com": "Cardinal Health",
        "cervey.com": "Cervey",
    }
    for key, name in known.items():
        if key in domain:
            return name
    if category == "internal":
        return "Creo"
    # capturerx.com → CaptureRx style
    base = domain.split(".")[0]
    return base.replace("-", " ").title()


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def compute_contact_rank(count: int, last_seen: str, max_count: int) -> float:
    """Higher = more important. Frequency + recency."""
    dt = _parse_dt(last_seen)
    recency = 0.0
    if dt:
        days_ago = (datetime.now(UTC) - dt).days
        recency = max(0.0, 1.0 - days_ago / 365.0)
    freq = count / max(max_count, 1)
    return round(0.7 * freq + 0.3 * recency, 4)


def assign_importance(rank_score: float, top_threshold: float, mid_threshold: float) -> str:
    if rank_score >= top_threshold:
        return "high"
    if rank_score >= mid_threshold:
        return "medium"
    return "low"


def scrape_inbox(
    max_pages: int = 50,
    page_size: int = 100,
    folder: str = "inbox",
) -> tuple[list[DomainStats], list[ContactStats]]:
    """Paginate inbox and aggregate domain/contact statistics."""
    backend = MsGraphBackend()
    messages = backend.list_messages_metadata(
        folder=folder,
        page_size=page_size,
        max_pages=max_pages,
    )

    domain_data: dict[str, DomainStats] = {}
    contact_data: dict[str, ContactStats] = {}
    domain_contacts: dict[str, set[str]] = defaultdict(set)

    for msg in messages:
        domain = extract_domain(msg.sender_email)
        if not domain:
            continue

        if domain not in domain_data:
            cat = suggest_category(domain)
            domain_data[domain] = DomainStats(
                domain=domain,
                suggested_category=cat,
                category=cat,
                company=suggest_company_name(domain, cat),
            )
        ds = domain_data[domain]
        ds.message_count += 1
        if not ds.first_seen or msg.received_at < ds.first_seen:
            ds.first_seen = msg.received_at
        if not ds.last_seen or msg.received_at > ds.last_seen:
            ds.last_seen = msg.received_at
        if len(ds.sample_subjects) < 5 and msg.subject and msg.subject not in ds.sample_subjects:
            ds.sample_subjects.append(msg.subject)
        if len(ds.sample_emails) < 5 and msg.subject:
            if not any(e.subject == msg.subject for e in ds.sample_emails):
                ds.sample_emails.append(
                    SampleEmail(
                        message_id=msg.message_id,
                        subject=msg.subject,
                        sender_email=msg.sender_email,
                        sender_name=msg.sender_name,
                        received_at=msg.received_at,
                        body_preview=(msg.body_preview or "")[:500],
                    )
                )
        domain_contacts[domain].add(msg.sender_email.lower())

        email_key = msg.sender_email.lower()
        if email_key not in contact_data:
            contact_data[email_key] = ContactStats(
                email=email_key,
                name=msg.sender_name,
                domain=domain,
                category=suggest_category(domain),
                company=suggest_company_name(domain, suggest_category(domain)),
            )
        cs = contact_data[email_key]
        cs.message_count += 1
        if msg.sender_name and not cs.name:
            cs.name = msg.sender_name
        if not cs.first_seen or msg.received_at < cs.first_seen:
            cs.first_seen = msg.received_at
        if not cs.last_seen or msg.received_at > cs.last_seen:
            cs.last_seen = msg.received_at
        if len(cs.sample_subjects) < 5 and msg.subject:
            cs.sample_subjects.append(msg.subject)

    for domain, emails in domain_contacts.items():
        domain_data[domain].contacts = sorted(emails)
        domain_data[domain].contact_count = len(emails)

    max_count = max((c.message_count for c in contact_data.values()), default=1)
    contacts = list(contact_data.values())
    for c in contacts:
        c.rank_score = compute_contact_rank(c.message_count, c.last_seen, max_count)

    contacts.sort(key=lambda x: (-x.rank_score, -x.message_count))

    if contacts:
        scores = [c.rank_score for c in contacts]
        top = scores[max(0, len(scores) // 10)] if len(scores) > 10 else scores[0]
        mid = scores[max(0, len(scores) // 3)] if len(scores) > 3 else scores[-1]
        for i, c in enumerate(contacts):
            c.importance = assign_importance(c.rank_score, top, mid)
            c.agent_enabled = i < min(20, len(contacts)) and c.importance in ("high", "medium")

    domains = sorted(domain_data.values(), key=lambda d: (-d.message_count, d.domain))
    return domains, contacts


def save_catalog(domains: list[DomainStats], contacts: list[ContactStats]) -> None:
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)

    existing_domains: dict[str, dict] = {}
    if DOMAINS_FILE.exists():
        raw = yaml.safe_load(DOMAINS_FILE.read_text(encoding="utf-8")) or {}
        for d in raw.get("domains", []):
            existing_domains[d["domain"]] = d

    domain_rows = []
    for d in domains:
        row = {
            "domain": d.domain,
            "message_count": d.message_count,
            "contact_count": d.contact_count,
            "first_seen": d.first_seen,
            "last_seen": d.last_seen,
            "suggested_category": d.suggested_category,
            "category": existing_domains.get(d.domain, {}).get("category", d.category),
            "company": existing_domains.get(d.domain, {}).get("company", d.company),
            "config_client_abbrev": existing_domains.get(d.domain, {}).get(
                "config_client_abbrev", getattr(d, "config_client_abbrev", None)
            ),
            "config_client_name": existing_domains.get(d.domain, {}).get(
                "config_client_name", getattr(d, "config_client_name", None)
            ),
            "sample_subjects": d.sample_subjects,
            "sample_emails": [
                {
                    "message_id": e.message_id,
                    "subject": e.subject,
                    "sender_email": e.sender_email,
                    "sender_name": e.sender_name,
                    "received_at": e.received_at,
                    "body_preview": e.body_preview,
                }
                for e in d.sample_emails
            ],
            "contacts": d.contacts[:10],
        }
        domain_rows.append(row)

    existing_contacts: dict[str, dict] = {}
    if CONTACTS_FILE.exists():
        raw = yaml.safe_load(CONTACTS_FILE.read_text(encoding="utf-8")) or {}
        for c in raw.get("contacts", []):
            existing_contacts[c["email"]] = c

    contact_rows = []
    for i, c in enumerate(contacts, 1):
        prev = existing_contacts.get(c.email, {})
        contact_rows.append(
            {
                "rank": i,
                "email": c.email,
                "name": c.name,
                "domain": c.domain,
                "message_count": c.message_count,
                "rank_score": c.rank_score,
                "importance": prev.get("importance", c.importance),
                "agent_enabled": prev.get("agent_enabled", c.agent_enabled),
                "category": prev.get("category", c.category),
                "company": prev.get("company", c.company),
                "first_seen": c.first_seen,
                "last_seen": c.last_seen,
                "sample_subjects": c.sample_subjects,
            }
        )

    DOMAINS_FILE.write_text(
        yaml.dump(
            {
                "scraped_at": datetime.now(UTC).isoformat(),
                "domain_count": len(domain_rows),
                "domains": domain_rows,
            },
            default_flow_style=False,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    CONTACTS_FILE.write_text(
        yaml.dump(
            {
                "scraped_at": datetime.now(UTC).isoformat(),
                "contact_count": len(contact_rows),
                "contacts": contact_rows,
            },
            default_flow_style=False,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def load_domain_categories() -> dict:
    """Load categories from team config, falling back to domain_categories.yaml."""
    from app.team_config import load_team_config

    team = load_team_config()
    if team.categories:
        return {"categories": team.categories, "hints": team.domain_hints}
    if CATEGORIES_FILE.exists():
        return yaml.safe_load(CATEGORIES_FILE.read_text(encoding="utf-8")) or {}
    return {"categories": CATEGORY_LABELS, "hints": DEFAULT_DOMAIN_HINTS}


def print_scrape_summary(domains: list[DomainStats], contacts: list[ContactStats]) -> None:
    print(f"\nScraped {sum(d.message_count for d in domains)} messages")
    print(f"Unique domains:  {len(domains)}")
    print(f"Unique contacts: {len(contacts)}\n")

    print("TOP DOMAINS (by volume)")
    print(f"{'Domain':<35} {'Msgs':>6} {'Cat':<15} {'Company'}")
    print("-" * 80)
    for d in domains[:25]:
        print(f"{d.domain:<35} {d.message_count:>6} {d.category:<15} {d.company or '—'}")

    print("\nTOP CONTACTS (by rank)")
    print(f"{'#':<4} {'Contact':<30} {'Email':<35} {'Msgs':>5} {'Imp':<6} Agent")
    print("-" * 95)
    for i, c in enumerate(contacts[:20], 1):
        name = (c.name or "?")[:28]
        agent = "yes" if c.agent_enabled else "no"
        print(f"{i:<4} {name:<30} {c.email:<35} {c.message_count:>5} {c.importance:<6} {agent}")

    print("\nCatalog saved:")
    print(f"  {DOMAINS_FILE}")
    print(f"  {CONTACTS_FILE}")
    print("\nNext: edit categories in inbox_domains.yaml, then run:")
    print("  email-assistant apply-catalog")
