# Phase 5: Studio UI — Email Settings Tab

**Agent:** `@email-settings-ui-agent`  
**Branch:** `feature/email-settings-auto-response`  
**Prerequisites:** Phase 4 complete (API routes live)

## Objective

Add the Email Settings panel to Studio SPA: Ollama status, templates, rules, run controls, and queues.

## Deliverables

| File | Action |
|------|--------|
| `app/web/static/index.html` | MODIFY — nav button + `#panel-email-settings` section |
| `app/web/static/app.js` | MODIFY — load/save handlers for all sub-panels |
| `app/web/static/styles.css` | MODIFY — rule cards, queue rows |
| `docs/STUDIO.md` | MODIFY — document new routes and panel |

## UI sections (in order)

1. **Ollama status** — health badge, model, host, "Run test prompt"
2. **Templates** — list, create/edit, "Draft with AI" → `/api/templates/ai-assist`
3. **Rules** — enable toggle, keywords, scope, mode, template picker, generation, delivery
4. **Run controls** — "Process inbox now", poller toggle + interval
5. **Approval queue** — Preview, Approve, Reject
6. **Auto queue** — read-only list with thread note links

## Validation

```bash
email-assistant ui
# Manual: open Email Settings tab, verify each section loads without console errors
```

## Exit criteria

- [x] Nav tab switches to Email Settings panel
- [x] CRUD for templates and rules works end-to-end
- [x] Process-now triggers job; approval queue refreshes
- [x] STUDIO.md updated
- [x] Plan moved to `completed/` when done

## Next phase

→ [phase6-email-settings-validation.md](phase6-email-settings-validation.md) with `@test-agent` + `@privacy-agent`
