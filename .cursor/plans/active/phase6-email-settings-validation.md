# Phase 6: Validation, Privacy, Release

**Agents:** `@test-agent`, `@privacy-agent`, `@reviewer-agent`  
**Branch:** `feature/email-settings-auto-response`  
**Prerequisites:** Phases 1–5 complete

## Objective

Full test coverage pass, privacy review, docs, and PR readiness.

## Tasks

1. **Tests** — fill gaps across all new modules; ensure no real network/Graph in tests
2. **Privacy** — confirm `data/queue/` gitignored; update `.cursor/rules/160-privacy-and-pii.mdc` if needed
3. **Docs** — README env table, STUDIO.md API section
4. **Review** — scope check, no auto-send enabled, no PII in committed files

## Validation (full suite)

```bash
ruff check .
black --check .
pytest tests/test_rule_engine.py tests/test_response_queue.py tests/test_email_rules_yaml.py tests/test_obsidian_writer.py -v
EMAIL_BACKEND=mock python run_local.py
email-assistant ui
```

## Exit criteria

- [ ] Full pytest suite green
- [ ] Lint/format clean
- [ ] Privacy checklist passed (`@privacy-agent`)
- [ ] Reviewer sign-off (`@reviewer-agent`)
- [ ] PR opened against `main`
- [ ] All phase plans moved to `completed/`
- [ ] Master plan moved to `completed/`

## Post-merge

Phase 2 follow-up plan (Graph send) — separate branch, not this feature.
