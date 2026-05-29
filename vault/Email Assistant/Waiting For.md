# Waiting For

#email-assistant #waiting

Things you are waiting to hear back on. The agent watches incoming mail for matching keywords and notifies you in [[Email Assistant/Inbox Review]].

**Canonical config:** `data/waiting_for.yaml` (repo root)

## Open items

| ID | Project | Waiting for | Keywords |
|----|---------|-------------|----------|
| `acme_schema_approval` | [[Projects/Acme Data Pipeline]] | [[Contacts/Jane Doe]] | schema approved, approval, approved data model |
| `northstar_refresh_timing` | [[Projects/Executive Dashboard]] | [[Contacts/Mark Lee]] | refresh schedule, daily refresh, data latency |

## Completed Items

*Agent moves completed items here with date and evidence.*

## How matching works

- Agent scans subject + body for keywords in `waiting_for.yaml`
- Strong match → category `waiting_info_arrived` → note appended to company/contact/project
- Set `UPDATE_WAITING_YAML=true` in `.env` to auto-close items in YAML (optional)

## Back to

[[Home]]

### 2026-05-24 — Completed: `acme_schema_approval`
Evidence: Information may have arrived for waiting item: acme_schema_approval

### 2026-05-24 — Completed: `northstar_refresh_timing`
Evidence: Information may have arrived for waiting item: northstar_refresh_timing

### 2026-05-24 — Completed: `acme_schema_approval`
Evidence: Information may have arrived for waiting item: acme_schema_approval

### 2026-05-24 — Completed: `northstar_refresh_timing`
Evidence: Information may have arrived for waiting item: northstar_refresh_timing

