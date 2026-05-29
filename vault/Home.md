# Email Assistant — Home

Welcome to your email knowledge base. This vault lives in the same repo as the agent (`vault/`) so you can sync it with Git, iCloud, or Obsidian Sync later.

## Quick links

| Area | Notes |
|------|--------|
| **Setup** | [[Email Assistant/Domain Catalog]] · `data/catalog/inbox_domains.yaml` |
| **Triage** | [[Email Assistant/Inbox Review]] · [[Email Assistant/Draft Replies]] · [[Email Assistant/Waiting For]] |
| **Companies** | See `vault/Companies/` — generated from inbox catalog |
| **Agents** | `agents/contacts/*.policy.md` — one per prioritized contact |

## Bootstrap workflow

```bash
email-assistant scrape-inbox          # discover domains & contacts
# Edit data/catalog/inbox_domains.yaml — set category per domain
email-assistant apply-catalog         # → companies.yaml, vault, agents
email-assistant run                   # process new mail
```

## Your vendor categories

| Category | Examples |
|----------|----------|
| 340B vendor | CaptureRx, Verity 340B, Cervey |
| Pharmacy | Retail, specialty, mail-order pharmacies |
| Wholesaler | Cardinal Health |
| Internal | Creo (`creocomp.com`) |

## How this vault works

1. **Machine-readable config** — `data/*.yaml` in the repo root (companies, contacts, projects, waiting-for).
2. **Human-readable memory** — Markdown notes here; the agent appends summaries after each run.
3. **You review** — High-priority items land in [[Email Assistant/Inbox Review]]; drafts in [[Email Assistant/Draft Replies]].

## Open waiting items

See [[Email Assistant/Waiting For]] for the full list. Agent config: `data/waiting_for.yaml`.

## Run the agent locally

```bash
# From repo root (OBSIDIAN_VAULT_PATH defaults to ./vault)
python run_local.py
```

## Folder conventions

| Folder | Purpose |
|--------|---------|
| `Companies/` | One note per company; email activity appended automatically |
| `Contacts/` | People; link back to company and projects |
| `Projects/` | Active workstreams |
| `Email Assistant/` | Agent-owned triage dashboards |
| `templates/` | Obsidian templates for manual notes |

## Tags

Use sparingly for views: `#company` `#contact` `#project` `#waiting` `#needs-response`
