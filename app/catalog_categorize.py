"""Apply user category rules to scraped inbox_domains.yaml."""

from __future__ import annotations

import yaml

from app.config import DATA_DIR
from app.inbox_catalog import DOMAINS_FILE, suggest_category, suggest_company_name


def _domain_rules_from_team() -> list[tuple[str, str, str | None]]:
    """Build rules from config/team.yaml domain_hints."""
    from app.team_config import load_team_config

    team = load_team_config()
    rules: list[tuple[str, str, str | None]] = []
    for pattern, category in team.domain_hints.items():
        rules.append((pattern, category, None))
    # Built-in noise patterns (appended after team hints)
    rules.extend(DOMAIN_RULES_BUILTIN)
    return rules


# Built-in patterns after team hints
DOMAIN_RULES_BUILTIN: list[tuple[str, str, str | None]] = [
    ("appriver.com", "partner", "AppRiver secure mail"),
    ("noreply", "newsletter", None),
    ("no-reply", "newsletter", None),
    ("notifications@", "newsletter", None),
]


def categorize_domains() -> int:
    if not DOMAINS_FILE.exists():
        raise FileNotFoundError(f"Run scrape-inbox first. Missing {DOMAINS_FILE}")

    raw = yaml.safe_load(DOMAINS_FILE.read_text(encoding="utf-8")) or {}
    updated = 0
    for row in raw.get("domains", []):
        domain = row.get("domain", "").lower()
        matched = False
        for pattern, category, company in _domain_rules_from_team():
            if pattern in domain or domain.endswith(pattern.lstrip("@")):
                row["category"] = category
                if company:
                    row["company"] = company
                elif not row.get("company"):
                    row["company"] = suggest_company_name(domain, category)
                matched = True
                updated += 1
                break
        if not matched and row.get("category") == "unassigned":
            cat = suggest_category(domain)
            row["category"] = cat
            if not row.get("company"):
                row["company"] = suggest_company_name(domain, cat)

    # Propagate domain category to contacts file
    contacts_path = DATA_DIR / "catalog" / "inbox_contacts.yaml"
    domain_cat = {d["domain"]: d for d in raw.get("domains", [])}
    if contacts_path.exists():
        contacts_raw = yaml.safe_load(contacts_path.read_text(encoding="utf-8")) or {}
        for c in contacts_raw.get("contacts", []):
            dom = c.get("domain", "")
            if dom in domain_cat:
                dom_cat = domain_cat[dom].get("category", "unassigned")
                imp = c.get("importance", "medium")
                # Preserve per-contact low/ignore override
                if imp == "low" or (
                    c.get("category") == "ignore"
                    and dom_cat not in ("ignore", "newsletter", "personal")
                ):
                    c["category"] = "ignore"
                    c["importance"] = "low"
                    c["agent_enabled"] = False
                else:
                    c["category"] = dom_cat
                    c["company"] = domain_cat[dom].get("company")
                    if dom_cat in ("ignore", "newsletter", "personal"):
                        c["agent_enabled"] = False
                    elif imp == "high":
                        c["agent_enabled"] = True
                    elif imp == "medium":
                        c["agent_enabled"] = True
                    else:
                        c["agent_enabled"] = False
        contacts_path.write_text(
            yaml.dump(contacts_raw, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

    DOMAINS_FILE.write_text(
        yaml.dump(raw, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return updated
