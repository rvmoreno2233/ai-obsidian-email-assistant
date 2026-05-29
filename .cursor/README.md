# Email Assistant Agent — Cursor Operating System

This `.cursor/` directory is the Skillport v2 scaffold for the Email Assistant Agent repo.

## Layers

| Layer | Path | Purpose |
|-------|------|---------|
| Rules | `rules/` | Persistent constraints (always-on and domain-specific) |
| Agents | `agents/universal/` | Reusable roles across repos |
| Agents | `agents/project/` | Email Assistant–specific workers |
| Plans | `plans/` | Durable task memory (`active/`, `completed/`, `archived/`) |
| Hooks | `hooks/` | Automated guardrails (quality gates, risky command blocks) |
| Prompts | `prompts/` | Reusable prompt starters |
| Checklists | `checklists/` | Human + agent review gates |
| Templates | `templates/` | Plan, rule, and agent templates |

## Quick start

1. Read `rules/000-repo-overview.mdc` for repo identity.
2. For multi-file work, use `@architect` to create a plan in `plans/active/`.
3. Implement with `@implementation-agent` referencing the plan.
4. Review with `@reviewer-agent` or `@security-agent`.
5. Run validation: `pytest`, `ruff check .`, `black --check .`

## Validation commands

```bash
pytest
ruff check .
black --check .
EMAIL_BACKEND=mock CLASSIFIER_MODE=rule RESPONDER_MODE=rule python run_local.py
```

## Project agents

| Agent | Use when |
|-------|----------|
| `graph-agent` | MSAL auth, Microsoft Graph backend, drafts |
| `catalog-agent` | Inbox scrape, categorize, store, apply pipeline |
| `studio-agent` | FastAPI Studio UI and background jobs |
| `pipeline-agent` | Classify, match, route, respond, `run_local.py` |
| `vault-agent` | Obsidian vault writes and layout |
| `config-json-agent` | Creo client registry and domain mapping |
| `team-config-agent` | `config/team.yaml`, categories, domain hints |
| `privacy-agent` | PII, tokens, catalog hygiene, commit safety |
| `azure-agent` | Azure Functions and Bicep deploy scaffold |
| `runtime-agent` | Kill/restart Studio UI (port, venv, health check) |

## Email Settings feature agents (phased)

| Phase | Agent | Plan |
|-------|-------|------|
| 1 | `email-settings-foundation-agent` | `plans/active/phase1-email-settings-foundation.md` |
| 2 | `email-settings-llm-agent` | `plans/active/phase2-email-settings-llm.md` |
| 3 | `email-settings-engine-agent` | `plans/active/phase3-email-settings-rule-engine.md` |
| 4 | `email-settings-api-agent` | `plans/active/phase4-email-settings-api-poller.md` |
| 5 | `email-settings-ui-agent` | `plans/active/phase5-email-settings-ui.md` |

Handoff prompt: `prompts/handoff-email-settings.md`

## Restart Studio

```bash
.cursor/scripts/restart-studio.sh restart
```

Dedicated port: `STUDIO_PORT` in `.env` (default `8080`).
