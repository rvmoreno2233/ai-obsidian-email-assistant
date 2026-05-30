# Phase 4: API & Poller — Studio Backend Routes

**Agent:** `@email-settings-api-agent`  
**Branch:** `feat/email-settings-phase4-api-poller`  
**Prerequisites:** Phase 3 complete  
**Status:** Complete (2026-05-30)

## Objective

Expose Email Settings via FastAPI routes and add a background poller wired into app lifespan.

## Deliverables

| File | Action |
|------|--------|
| `app/inbox_processor.py` | NEW — shared `process_inbox()` for CLI, jobs, poller |
| `app/web/poller.py` | NEW — `BackgroundPoller` asyncio task |
| `app/web/app.py` | MODIFY — routes + lifespan start/stop poller |
| `app/email_rules.py` | MODIFY — CRUD helpers for rules/templates |
| `run_local.py` | MODIFY — delegates to `process_inbox()` |
| `tests/test_studio_api.py` | NEW — API and poller tests |

## API routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/ollama/health` | Ollama status |
| POST | `/api/ollama/test` | Latency test chat |
| GET/POST | `/api/templates` | List/create templates |
| PATCH/DELETE | `/api/templates/{id}` | Update/delete template |
| POST | `/api/templates/ai-assist` | Ollama drafts template body |
| GET/POST | `/api/rules` | List/create rules |
| PATCH/DELETE | `/api/rules/{id}` | Update/delete rule |
| GET/PUT | `/api/email-settings/poller` | Poller config + last run stats |
| POST | `/api/email-settings/process-now` | Background job: process inbox |
| GET | `/api/queue/approval` | Pending approval items |
| POST | `/api/queue/approval/{id}/approve` | Mark approved (Phase 1: no Graph send) |
| POST | `/api/queue/approval/{id}/reject` | Mark rejected |
| GET | `/api/queue/auto` | Read-only auto queue |

## Poller behavior

- Same `process_inbox()` as manual button
- Interval from `POLLER_INTERVAL_SECONDS`
- Resume cursor from `data/queue/poller_state.json`
- Stop cleanly on FastAPI shutdown

## Tests

- API route tests with TestClient (mock backend, no Graph)
- Poller state persistence test

## Validation

```bash
pytest tests/test_studio_api.py -v
EMAIL_BACKEND=mock RULE_ENGINE_ENABLED=true python run_local.py
email-assistant ui  # routes respond (manual)
```

## Exit criteria

- [x] All routes registered and return expected shapes
- [x] `process-now` uses existing job runner pattern
- [x] Poller starts/stops with Studio lifespan
- [x] Approve/reject updates queue JSONL
- [x] Plan moved to `completed/` when done

## Next phase

→ [phase5-email-settings-ui.md](../active/phase5-email-settings-ui.md) with `@email-settings-ui-agent`
