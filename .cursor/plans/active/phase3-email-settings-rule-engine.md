# Phase 3: Rule Engine — Match, Render, Process, Router Hook

**Agent:** `@email-settings-engine-agent`  
**Branch:** `feature/email-settings-auto-response`  
**Prerequisites:** Phases 1–2 complete

## Objective

Build the rule engine and wire it into the existing pipeline so matched emails go to the queue instead of the legacy draft path.

## Deliverables

| File | Action |
|------|--------|
| `app/rule_engine.py` | NEW — `match_rules`, `render_template`, `fill_template_with_llm`, `process_email` |
| `app/action_router.py` | MODIFY — call `rule_engine.process(email)` first; short-circuit on match |

## Behavior

1. `match_rules(email)` — keyword match on subject/body per rule `scope` and `mode`
2. `render_template()` — substitute `{sender_first_name}`, `{team_name}`, etc.
3. `fill_template_with_llm()` — uses `prompts/template_fill.md` + `chat_text()`
4. `process_email()` — log → thread note → generate body → enqueue (approval or auto) → create Outlook draft via backend
5. Respect contact importance gate from classifier before rule matching
6. Honor `RULE_ENGINE_ENABLED` env flag

## Tests

- `tests/test_rule_engine.py` — keyword scopes, canned vs llm generation, delivery routing

## Validation

```bash
pytest tests/test_rule_engine.py tests/test_action_router.py -v
EMAIL_BACKEND=mock RULE_ENGINE_ENABLED=true python run_local.py
```

## Exit criteria

- [ ] Matched emails skip legacy draft and land in queue
- [ ] Unmatched emails use existing ActionRouter path
- [ ] LLM fill runs in background-safe context (no poller block — defer to Phase 4 job thread)
- [ ] All Phase 3 tests pass
- [ ] Plan moved to `completed/` when done

## Next phase

→ [phase4-email-settings-api-poller.md](phase4-email-settings-api-poller.md) with `@email-settings-api-agent`
