# Email Assistant Agent

Local-first email assistant that classifies Outlook mail, matches companies/contacts/projects, detects awaited information, updates Obsidian notes, and drafts replies for your review.

**MVP does not auto-send email.** Drafts only.

## Features

- Rule-based classifier with optional Ollama LLM layer
- YAML knowledge base (companies, contacts, projects, waiting-for items)
- Obsidian Markdown vault updates
- Microsoft Graph read + draft creation (MSAL device code flow)
- Azure Functions deployment scaffold (timer + queue)

## Quick start

```bash
python3.12 -m venv .venv   # Python 3.11+ required
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

# Obsidian: open vault/ in Obsidian (see vault/README.md)
# Agent writes to vault/ by default — no OBSIDIAN_VAULT_PATH required

# Run with mock emails (no Graph, no Ollama)
EMAIL_BACKEND=mock CLASSIFIER_MODE=rule RESPONDER_MODE=rule python run_local.py

# Run tests
pytest
```

## Environment variables

| Variable | Description |
|----------|-------------|
| `EMAIL_BACKEND` | `mock` (default) or `graph` |
| `CLASSIFIER_MODE` | `rule` or `llm` |
| `RESPONDER_MODE` | `rule` or `llm` |
| `OBSIDIAN_VAULT_PATH` | Path to Obsidian vault (default: `./vault`) |
| `OLLAMA_HOST` | Ollama API URL (default `http://127.0.0.1:11434`) |
| `OLLAMA_MODEL` | Model name (default `llama3.1`) |
| `MSGRAPH_CLIENT_ID` | Azure AD app client ID |
| `MSGRAPH_TENANT_ID` | Azure AD tenant ID |
| `MSGRAPH_SCOPES` | Graph scopes (default `Mail.Read Mail.ReadWrite`) |
| `AUTO_SEND_MODE` | `off` (MVP default), `safe`, or `full` |
| `STUDIO_HOST` | Studio bind address (default `127.0.0.1`) |
| `STUDIO_PORT` | Studio port (default `8080`) |
| `DATA_DIR` | YAML catalogs and rules path (default `data`) |
| `QUEUE_DIR` | Runtime response queues (default `data/queue`, gitignored) |
| `RULE_ENGINE_ENABLED` | Enable keyword auto-response rules (default `false`) |
| `POLLER_INTERVAL_SECONDS` | Background poller interval (default `300`) |
| `UPDATE_WAITING_YAML` | Persist waiting-item closures to YAML (default `false`) |

## Microsoft Graph setup

1. Register an app in [Azure Portal](https://portal.azure.com) → App registrations.
2. Add redirect URI: `http://localhost` (mobile/desktop).
3. API permissions: `Mail.Read`, `Mail.ReadWrite`, `offline_access`.
4. Enable public client flows.
5. Set `MSGRAPH_CLIENT_ID` in `.env`.
6. Authenticate: `email-assistant authenticate`

## Ollama

Install [Ollama](https://ollama.com) and pull a model:

```bash
ollama pull llama3.1
```

Set `CLASSIFIER_MODE=llm` and `RESPONDER_MODE=llm` to use structured outputs.

## Email Assistant Studio (web UI)

Visual editor for domain catalog, contacts, and team config:

```bash
email-assistant ui
```

See [docs/STUDIO.md](docs/STUDIO.md) for team deployment.

## Obsidian vault

The in-repo vault at [`vault/`](vault/) is your human-readable knowledge base:

- Open `vault/` as a vault in Obsidian (start at [[Home]])
- Agent appends email summaries to Companies, Contacts, Projects, and Email Assistant notes
- YAML catalogs in `data/` remain the source of truth for matching

## Project layout

```
app/           Core modules
data/          YAML catalogs (machine-readable)
data/catalog/  Scraped inbox domains & contacts (you categorize here)
vault/         Obsidian vault (human-readable, sync-ready)
agents/        Per-contact agent policies
prompts/       LLM prompt templates
tests/         Pytest suite
azure/         Azure Functions + Bicep
run_local.py   Local orchestration entrypoint
```

## CLI

```bash
email-assistant run      # Process recent emails
email-assistant test     # Run pytest
email-assistant authenticate  # MSAL device code login
```

## Azure deployment

See [azure/README.md](azure/README.md).

## License

MIT
