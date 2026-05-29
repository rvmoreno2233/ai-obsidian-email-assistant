# Phase 1: Foundation — Models, Queue, Config, Thread Notes

**Agent:** `@email-settings-foundation-agent`  
**Branch:** `feature/email-settings-auto-response`  
**Prerequisites:** Origin published on `main`  
**Status:** Complete (2026-05-29)

## Objective

Establish persistent data models, queue storage, config/env wiring, and vault thread-note append — no rule logic or UI yet.

## Deliverables

| File | Action |
|------|--------|
| `app/email_rules.py` | NEW — Pydantic models + YAML load/save for rules and templates |
| `app/response_queue.py` | NEW — JSONL queue store under `data/queue/` |
| `app/obsidian_writer.py` | MODIFY — `append_to_thread(email, classification, draft)` |
| `app/config.py` | MODIFY — `RULE_ENGINE_ENABLED`, `POLLER_INTERVAL_SECONDS`, `QUEUE_DIR` |
| `.env.example` | MODIFY — document new env vars |
| `.gitignore` | MODIFY — ignore `data/queue/` |
| `data/email_rules.yaml` | NEW — empty scaffold |
| `data/response_templates.yaml` | NEW — empty scaffold |

## Data shapes

See master plan: `email_rules.yaml`, `response_templates.yaml`, queue JSONL record shape.

## Tests

- `tests/test_email_rules_yaml.py` — round-trip load/save, validation
- `tests/test_response_queue.py` — append, update status, thread-safe mirror
- `tests/test_obsidian_writer.py` — append_to_thread creates/appends slug file

## Validation

```bash
pytest tests/test_email_rules_yaml.py tests/test_response_queue.py tests/test_obsidian_writer.py -v
ruff check app/email_rules.py app/response_queue.py
black --check app/email_rules.py app/response_queue.py
```

## Exit criteria

- [x] Models validate example YAML from master plan
- [x] Queue persists across reload; `data/queue/` gitignored
- [x] Thread slug from `(sender_domain, normalized subject root)`
- [x] All Phase 1 tests pass
- [x] Plan moved to `completed/` when done

## Next phase

→ [phase2-email-settings-llm.md](../active/phase2-email-settings-llm.md) with `@email-settings-llm-agent`
