# Email Assistant Studio

Web UI for categorizing inbox domains, ranking contacts, and syncing the Obsidian vault + agent policies.

## Start the app

```bash
source .venv/bin/activate
pip install -e ".[dev]"   # includes fastapi + uvicorn
email-assistant authenticate   # once per machine
email-assistant ui
```

Opens **http://127.0.0.1:8080**

## Team deployment

Each teammate:

1. Clone the repo
2. Copy `.env.example` → `.env` and set their own `MSGRAPH_CLIENT_ID` (or shared app registration)
3. Share `config/team.yaml` via Git (categories + domain hints)
4. Run `email-assistant authenticate` then `email-assistant ui`

Shared via Git:

| Path | Purpose |
|------|---------|
| `config/team.yaml` | Categories, domain hints, tenant ID, scrape defaults |
| `data/catalog/` | Scraped domains/contacts (optional — each user may scrape their own inbox) |
| `vault/` | Obsidian knowledge base |
| `agents/` | Per-contact policies |

Per-user (not committed):

| Path | Purpose |
|------|---------|
| `.env` | Graph client ID, personal paths |
| `~/.cache/email-assistant/msal_cache.json` | OAuth token |

## Workflow in the UI

1. **Domains → Preview** on a row — see sample email subject + body
2. **Suggest** — auto-match against `config.json` clients
3. **Map domain → client** — links domain to `client_abbrev`
4. **Actions → Apply to vault** — creates `vault/Clients/{abbrev}.md` notes

## API

The UI uses REST endpoints under `/api/` — useful for future integrations.
