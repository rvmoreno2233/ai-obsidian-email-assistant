# Phase 2: LLM Layer — Ollama Health, Chat, Prompts

**Agent:** `@email-settings-llm-agent`  
**Branch:** `feature/email-settings-auto-response`  
**Prerequisites:** Phase 1 complete  
**Status:** Complete (2026-05-29)

## Objective

Extend the LLM client for template assist/fill and add prompt files. No rule engine or API routes yet.

## Deliverables

| File | Action |
|------|--------|
| `app/llm_client.py` | MODIFY — `health_check()`, `chat_text()` |
| `prompts/template_assist.md` | NEW — draft a reply template from description |
| `prompts/template_fill.md` | NEW — fill template using original email |

## Behavior

- `health_check()` — GET Ollama `/api/tags`, return `{ok, model, host, models_available}`
- `chat_text()` — unstructured chat for template assist/fill (no structured output schema)
- Prompts use placeholders documented in master plan

## Tests

- Extend or add tests mocking Ollama HTTP (no real network)
- Health check returns `ok: false` when host unreachable
- `chat_text()` returns stripped response text

## Validation

```bash
pytest tests/test_llm_client.py -v  # create if missing
ruff check app/llm_client.py
```

## Exit criteria

- [x] `health_check()` and `chat_text()` implemented with timeouts
- [x] Both prompt files committed with clear instructions
- [x] Mock Ollama tests pass
- [x] Plan moved to `completed/` when done

## Next phase

→ [phase3-email-settings-rule-engine.md](../active/phase3-email-settings-rule-engine.md) with `@email-settings-engine-agent`
