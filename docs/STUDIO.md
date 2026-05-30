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
| `data/queue/` | Approval/auto queues, poller cursor, processing log |

## Workflow in the UI

1. **Domains → Preview** on a row — see sample email subject + body
2. **Suggest** — auto-match against `config.json` clients
3. **Map domain → client** — links domain to `client_abbrev`
4. **Actions → Apply to vault** — creates `vault/Clients/{abbrev}.md` notes
5. **Email Settings** — configure Ollama, reply templates, keyword rules, poller, and approval queues

## Email Settings tab

The **Email Settings** panel covers the auto-response pipeline (drafts only — nothing is auto-sent).

| Section | Purpose |
|---------|---------|
| Ollama | Health check, model/host display, test prompt |
| Templates | CRUD for reply templates; **Draft with AI** calls `/api/templates/ai-assist` |
| Rules | Keyword rules with scope, template, generation (canned/LLM), delivery (approval/auto) |
| Run controls | **Process inbox now** job; background poller enable + interval |
| Approval queue | Preview pending drafts; Approve / Reject |
| Auto queue | Read-only list of auto-queued drafts with thread note links |

Poller state persists to `data/queue/poller_state.json`. Enable via the UI or:

```bash
curl -X PUT http://127.0.0.1:8080/api/email-settings/poller \
  -H 'Content-Type: application/json' \
  -d '{"enabled": true, "interval_seconds": 300}'
```

## API

The UI uses REST endpoints under `/api/` — useful for future integrations.

### Catalog & team

- `/api/status`, `/api/domains`, `/api/contacts`, `/api/team`, `/api/clients` — catalog CRUD
- Job endpoints for scrape, categorize, and apply

### Email Settings (Phase 4+)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/ollama/health` | Ollama connectivity |
| POST | `/api/ollama/test` | Test prompt |
| GET/POST | `/api/templates` | List / create templates |
| PATCH/DELETE | `/api/templates/{id}` | Update / delete template |
| POST | `/api/templates/ai-assist` | AI template draft |
| GET/POST | `/api/rules` | List / create rules |
| PATCH/DELETE | `/api/rules/{id}` | Update / delete rule |
| GET/PUT | `/api/email-settings/poller` | Poller state |
| POST | `/api/email-settings/process-now` | Manual inbox run |
| GET | `/api/queue/approval` | Approval queue |
| POST | `/api/queue/approval/{id}/approve` | Approve entry |
| POST | `/api/queue/approval/{id}/reject` | Reject entry |
| GET | `/api/queue/auto` | Auto queue |
