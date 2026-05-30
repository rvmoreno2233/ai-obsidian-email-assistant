# Handoff: Email Settings & Auto-Response Pipeline

Copy this prompt when starting a new chat or phase. Replace `[PHASE N]` and check completed items.

---

## Context

Implementing **Email Settings** tab and keyword-triggered auto-response pipeline on branch `feat/email-settings-phase5-ui`.

- **Master plan:** `.cursor/plans/active/email-settings-master.md`
- **Architect source:** `.cursor/plans/email_settings_auto-response_b94c774f.plan.md`
- **Repo:** https://github.com/rvmoreno2233/ai-obsidian-email-assistant
- **MVP:** Drafts only. `AUTO_SEND_MODE=off`. Approve = mark queue entry; user sends from Outlook.

## Current phase

**Active:** Phase 6 — Validation & release  
**Agent:** `@test-agent`, `@privacy-agent`, `@reviewer-agent`  
**Plan file:** `.cursor/plans/active/phase6-email-settings-validation.md`

## Progress checklist

Mark `[x]` when a phase is fully done (tests pass, plan moved to `completed/`).

### Phase 1 — Foundation
- [x] `app/email_rules.py` (models + YAML I/O)
- [x] `app/response_queue.py` (JSONL queues)
- [x] `app/obsidian_writer.append_to_thread`
- [x] Config: `RULE_ENGINE_ENABLED`, `POLLER_INTERVAL_SECONDS`, `QUEUE_DIR`
- [x] `.gitignore` includes `data/queue/`
- [x] Tests: `test_email_rules_yaml`, `test_response_queue`, thread note tests
- [x] **Agent:** `@email-settings-foundation-agent`

### Phase 2 — LLM
- [x] `llm_client.health_check()` + `chat_text()`
- [x] `prompts/template_assist.md`, `prompts/template_fill.md`
- [x] Mock Ollama tests
- [x] **Agent:** `@email-settings-llm-agent`

### Phase 3 — Rule engine
- [x] `app/rule_engine.py` (match, render, fill, process)
- [x] `action_router.py` hook (rule engine first)
- [x] `tests/test_rule_engine.py`
- [x] **Agent:** `@email-settings-engine-agent`

### Phase 4 — API & poller
- [x] `app/web/poller.py` + lifespan wiring
- [x] All `/api/ollama`, `/api/templates`, `/api/rules`, `/api/email-settings`, `/api/queue` routes
- [x] API/poller tests
- [x] **Agent:** `@email-settings-api-agent`

### Phase 5 — UI
- [x] Email Settings nav + panel in `index.html`
- [x] Handlers in `app.js`, styles in `styles.css`
- [x] `docs/STUDIO.md` updated
- [x] Manual smoke test passed
- [x] **Agent:** `@email-settings-ui-agent`

### Phase 6 — Validation & release
- [ ] Full pytest + ruff + black
- [ ] `@privacy-agent` review (`data/queue/` PII)
- [ ] `@reviewer-agent` sign-off
- [ ] PR to `main`

---

## Session starter prompt (paste below)

```
Implement Email Settings Phase [N] per `.cursor/plans/active/phase[N]-email-settings-*.md`.

Use agent: @[phase-agent]
Read handoff: `.cursor/prompts/handoff-email-settings.md`
Branch: feature/email-settings-auto-response

Constraints:
- Drafts only (AUTO_SEND_MODE=off)
- Follow `.cursor/rules/` especially 030-architecture, 020-security, 160-privacy
- Add tests for new behavior
- Update handoff checklist when phase completes
- Do not start next phase until exit criteria met

When done:
1. Run phase validation commands from the plan
2. Mark checklist items [x] in handoff-email-settings.md
3. Move completed phase plan to `.cursor/plans/completed/`
4. Summarize changed files and test results
```

---

## Phase transition ritual

1. **Verify exit criteria** from completed phase plan (all boxes checked).
2. **Run validation commands** listed in that phase plan.
3. **Move plan** `active/phaseN-*.md` → `completed/phaseN-*.md`.
4. **Update checklist** above (mark phase `[x]`).
5. **Start fresh chat** with session starter prompt for next phase.
6. **Optional commit** per phase: `feat(email-settings): phase N — <short description>`

## Agent quick reference

| Phase | Agent | Base agents |
|-------|-------|-------------|
| 1 | `@email-settings-foundation-agent` | vault, pipeline |
| 2 | `@email-settings-llm-agent` | pipeline |
| 3 | `@email-settings-engine-agent` | pipeline |
| 4 | `@email-settings-api-agent` | studio, pipeline |
| 5 | `@email-settings-ui-agent` | studio |
| 6 | `@test-agent`, `@privacy-agent`, `@reviewer-agent` | universal |

## Blockers log

| Date | Phase | Blocker | Resolution |
|------|-------|---------|------------|
| | | | |
