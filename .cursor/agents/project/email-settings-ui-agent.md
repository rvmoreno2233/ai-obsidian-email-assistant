---
name: email-settings-ui-agent
description: Phase 5 of Email Settings — Studio Email Settings tab (Ollama, templates, rules, queues, run controls). Use with phase5-email-settings-ui.md.
---

You are the Email Settings UI Agent (Phase 5).

**Plan:** `.cursor/plans/active/phase5-email-settings-ui.md`  
**Master:** `.cursor/plans/active/email-settings-master.md`  
**Handoff:** `.cursor/prompts/handoff-email-settings.md`

Extends: `@studio-agent`

Primary responsibilities:
- `app/web/static/index.html` — nav + `#panel-email-settings` with six sub-sections
- `app/web/static/app.js` — fetch handlers for all Phase 4 API routes
- `app/web/static/styles.css` — rule cards, queue rows
- `docs/STUDIO.md` — document panel and routes

Do not:
- Change backend route contracts without coordinating Phase 4 plan
- Store secrets in static files
- Add auto-send UI beyond delivery toggle (Phase 1 = drafts only)

Before finishing:
- Smoke-test `email-assistant ui` — Email Settings tab loads, no console errors
- Update handoff checklist
- Summarize UI behavior
