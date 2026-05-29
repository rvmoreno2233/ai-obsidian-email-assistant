"""Apply inbox catalog to companies.yaml, vault notes, and agent policies."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from app.config import DATA_DIR, PROJECT_ROOT
from app.inbox_catalog import (
    CATEGORIES_FILE,
    CATEGORY_LABELS,
    CONTACT_IMPORTANCE_LABELS,
    CONTACTS_FILE,
    DEFAULT_DOMAIN_HINTS,
    DOMAINS_FILE,
)

AGENTS_DIR = PROJECT_ROOT / "agents"
VAULT_DIR = PROJECT_ROOT / "vault"


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def apply_catalog(
  min_messages: int = 3,
  agent_importance: tuple[str, ...] = ("high", "medium"),
) -> dict[str, int]:
    """Generate companies.yaml entries, Obsidian notes, and agent policies."""
    domains_raw = _load_yaml(DOMAINS_FILE)
    contacts_raw = _load_yaml(CONTACTS_FILE)
    if not domains_raw.get("domains"):
        raise FileNotFoundError(
            f"No domain catalog at {DOMAINS_FILE}. Run: email-assistant scrape-inbox"
        )

    stats = {"companies": 0, "contacts": 0, "vault_notes": 0, "agents": 0, "clients": 0}

    # Group domains by company name (user-assigned or suggested)
    companies: dict[str, dict] = {}
    for d in domains_raw["domains"]:
        if d.get("message_count", 0) < min_messages and d.get("category") == "unassigned":
            continue
        cat = d.get("category", "unassigned")
        if cat in ("ignore", "newsletter", "personal"):
            continue
        company = d.get("company") or d["domain"].split(".")[0].title()
        if company not in companies:
            companies[company] = {
                "name": company,
                "domains": [],
                "keywords": [],
                "category": cat,
                "contacts": [],
            }
        companies[company]["domains"].append(d["domain"])
        companies[company]["contacts"].extend(d.get("contacts", []))

    # Merge contacts
    contact_by_email: dict[str, dict] = {}
    for c in contacts_raw.get("contacts", []):
        contact_by_email[c["email"]] = c

    for company in companies.values():
        company["contacts"] = sorted(set(company["contacts"]))
        company["domains"] = sorted(set(company["domains"]))

    # Write companies.yaml (merge with seeds, drop demo Acme/Northstar if real data exists)
    companies_yaml = {"companies": []}
    for c in sorted(companies.values(), key=lambda x: x["name"]):
        companies_yaml["companies"].append(
            {
                "name": c["name"],
                "domains": c["domains"],
                "keywords": [c["category"]] if c["category"] != "unassigned" else [],
                "category": c["category"],
                "contacts": c["contacts"][:50],
            }
        )
    (DATA_DIR / "companies.yaml").write_text(
        yaml.dump(companies_yaml, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    stats["companies"] = len(companies_yaml["companies"])

    # contacts.yaml for agent matching
    contacts_out = []
    for c in contacts_raw.get("contacts", []):
        imp = c.get("importance", "medium")
        if imp == "low" or c.get("category") in ("ignore", "newsletter"):
            continue
        contacts_out.append(
            {
                "name": c.get("name") or c["email"].split("@")[0],
                "email": c["email"],
                "company": c.get("company"),
                "importance": imp,
                "agent_enabled": imp in ("high", "medium"),
                "category": c.get("category"),
                "notes": [
                    f"Rank #{c.get('rank', '?')}, {c.get('message_count', 0)} messages",
                    CONTACT_IMPORTANCE_LABELS.get(imp, imp),
                ],
            }
        )
    (DATA_DIR / "contacts.yaml").write_text(
        yaml.dump({"contacts": contacts_out}, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    stats["contacts"] = len(contacts_out)

    # Obsidian vault notes
    for company in companies.values():
        _write_company_note(company)
        stats["vault_notes"] += 1

    for c in contacts_raw.get("contacts", []):
        imp = c.get("importance", "medium")
        if imp == "low":
            continue
        if imp not in ("high", "medium"):
            continue
        _write_contact_note(c)
        stats["vault_notes"] += 1
        _write_agent_policy(c)
        stats["agents"] += 1

    _write_domain_catalog_note(domains_raw)
    _write_category_reference()
    stats["vault_notes"] += 2

    stats["clients"] = _write_client_vault_notes(domains_raw)

    return stats


def _write_client_vault_notes(domains_raw: dict) -> int:
    """Create Obsidian client folders for domains mapped to config.json clients."""
    from app.config_json import get_client_by_abbrev

    clients_dir = VAULT_DIR / "Clients"
    clients_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, dict] = {}
    count = 0

    for d in domains_raw.get("domains", []):
        abbrev = d.get("config_client_abbrev")
        if not abbrev:
            continue
        client = get_client_by_abbrev(abbrev)
        if not client:
            continue

        key = abbrev.lower()
        if key not in mapping:
            mapping[key] = {
                "client_abbrev": abbrev,
                "client_name": client.client_name,
                "340b_id": client.b340_id,
                "verity_abbrev": client.verity_abbrev,
                "domains": [],
            }
        mapping[key]["domains"].append(d["domain"])

        note_path = clients_dir / f"{abbrev}.md"
        domains_list = ", ".join(f"`{x}`" for x in sorted(set(mapping[key]["domains"])))
        content = f"""# {client.client_name}

#client #config-json

| | |
|---|---|
| **Abbrev** | `{abbrev}` |
| **340B ID** | {client.b340_id or '—'} |
| **Verity** | {client.verity_abbrev or '—'} |
| **EMR** | {client.emr or '—'} |
| **Archive** | {client.archive_dir or '—'} |

## Linked domains

{domains_list}

## Recent Email Activity

*Agent appends important emails below.*

## Config

Source: `config.json` → `client_abbrev: {abbrev}`

## Back to

[[Home]] · [[Email Assistant/Domain Catalog]]
"""
        note_path.write_text(content, encoding="utf-8")
        count += 1

    if mapping:
        (DATA_DIR / "client_domain_map.yaml").write_text(
            yaml.dump({"clients": list(mapping.values())}, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

    return count


def _write_company_note(company: dict) -> None:
    path = VAULT_DIR / "Companies" / f"{company['name']}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    cat = company.get("category", "unassigned")
    contacts_links = "\n".join(
        f"- [[Contacts/{e.split('@')[0].replace('.', ' ').title()}]] ({e})"
        for e in company.get("contacts", [])[:15]
    )
    domains = ", ".join(f"`{d}`" for d in company.get("domains", []))
    content = f"""# {company['name']}

#company #{cat.replace('_', '-')}

**Category:** {CATEGORY_LABELS.get(cat, cat)}  
**Domains:** {domains}

## Contacts

{contacts_links or '- _(none yet)_'}

## Recent Email Activity

*Agent appends summaries below this heading.*

## Back to

[[Home]] · [[Email Assistant/Domain Catalog]]
"""
    if not path.exists():
        path.write_text(content, encoding="utf-8")
    else:
        # Update header block only if new
        existing = path.read_text(encoding="utf-8")
        if domains not in existing:
            path.write_text(content, encoding="utf-8")


def _write_contact_note(contact: dict) -> None:
    name = contact.get("name") or contact["email"].split("@")[0]
    safe_name = _safe_note_name(name)
    path = VAULT_DIR / "Contacts" / f"{safe_name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    company = contact.get("company") or "Unknown"
    content = f"""# {name}

#contact

| | |
|---|---|
| **Email** | {contact['email']} |
| **Company** | [[Companies/{company}]] |
| **Category** | {contact.get('category', 'unassigned')} |
| **Importance** | {contact.get('importance', 'medium')} |
| **Messages** | {contact.get('message_count', 0)} |
| **Agent** | {'enabled' if contact.get('agent_enabled') else 'disabled'} |

## Agent policy

[[agents/contacts/{_agent_slug(contact)}]]

## Recent Email Activity

*Agent appends summaries below this heading.*

## Back to

[[Home]]
"""
    path.write_text(content, encoding="utf-8")


def _write_agent_policy(contact: dict) -> None:
    slug = _agent_slug(contact)
    path = AGENTS_DIR / "contacts" / f"{slug}.policy.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    name = contact.get("name") or contact["email"]
    company = contact.get("company") or "Unknown"
    imp = contact.get("importance", "medium")
    mode = CONTACT_IMPORTANCE_LABELS.get(imp, imp)
    if imp == "high":
        processing = "Process **all** email from this contact (always on)."
    elif imp == "medium":
        processing = (
            "Process email **only when keywords match** subject or body "
            "(see sample subjects and company keywords below)."
        )
    else:
        processing = "Do not process (ignored)."
    content = f"""# Agent Policy — {name}

Contact: {contact['email']}  
Company: {company}  
Importance: {imp} — {mode}  
Category: {contact.get('category', 'unassigned')}

## Processing mode

{processing}

## High priority triggers

- Direct questions from this contact
- Mentions of blockers, deadlines, or approvals
- Thread replies where you are explicitly @mentioned

## Keyword filters (medium importance)

Use sample subjects and company/project keywords before drafting.

## Never auto-send

- Legal, pricing, HIPAA, or contractual commitments
- Patient-specific or PHI content
- Anything requiring judgment — draft only

## Draft tone

- Concise, professional, action-oriented
- Match formality of incoming mail

## Sample subjects (from inbox)

{chr(10).join(f'- {s}' for s in contact.get('sample_subjects', [])[:5]) or '- _(none)_'}

## Default project

_(assign in data/projects.yaml if applicable)_
"""
    path.write_text(content, encoding="utf-8")


def _write_domain_catalog_note(domains_raw: dict) -> None:
    path = VAULT_DIR / "Email Assistant" / "Domain Catalog.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Domain Catalog",
        "",
        "#email-assistant",
        "",
        f"Scraped: {domains_raw.get('scraped_at', 'unknown')}",
        f"Domains: {domains_raw.get('domain_count', 0)}",
        "",
        "Edit categories in `data/catalog/inbox_domains.yaml`, then run `email-assistant apply-catalog`.",
        "",
        "| Domain | Msgs | Category | Company |",
        "|--------|------|----------|---------|",
    ]
    for d in domains_raw.get("domains", [])[:100]:
        lines.append(
            f"| `{d['domain']}` | {d.get('message_count', 0)} | "
            f"{d.get('category', '?')} | {d.get('company', '—')} |"
        )
    if domains_raw.get("domain_count", 0) > 100:
        lines.append(f"\n_…and {domains_raw['domain_count'] - 100} more in YAML._")
    lines.append("\n## Back to\n\n[[Home]]")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_category_reference() -> None:
    path = DATA_DIR / "domain_categories.yaml"
    if not path.exists():
        path.write_text(
            yaml.dump(
                {"categories": CATEGORY_LABELS, "hints": DEFAULT_DOMAIN_HINTS},
                default_flow_style=False,
            ),
            encoding="utf-8",
        )


def _safe_note_name(name: str) -> str:
    return name.strip()[:80]


def _agent_slug(contact: dict) -> str:
    email = contact["email"].split("@")[0]
    return re.sub(r"[^a-z0-9]+", "_", email.lower()).strip("_")
