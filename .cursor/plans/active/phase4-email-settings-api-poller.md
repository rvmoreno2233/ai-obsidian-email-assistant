# Phase 4: API & Poller — Studio Backend Routes

**Agent:** `@email-settings-api-agent`  
**Branch:** `feature/email-settings-auto-response`  
**Prerequisites:** Phase 3 complete

## Objective

Expose Email Settings via FastAPI routes and add a background poller wired into app lifespan.

## Deliverables

| File | Action |
|------|--------|
| `app/web/poller.py` | NEW — `BackgroundPoller` asyncio task |
| `app/web/app.py` | MODIFY — routes + lifespan start/stop poller |

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
pytest tests/test_studio_api.py -v -k "email_settings or ollama or queue"  # add as needed
email-assistant ui  # routes respond (manual)
```

## Exit criteria

- [ ] All routes registered and return expected shapes
- [ ] `process-now` uses existing job runner pattern
- [ ] Poller starts/stops with Studio lifespan
- [ ] Approve/reject updates queue JSONL
- [ ] Plan moved to `completed/` when done

## Next phase

→ [phase5-email-settings-ui.md](phase5-email-settings-ui.md) with `@email-settings-ui-agent`
