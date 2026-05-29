# Plan: Skillport v2 initialization

## Goal

Initialize `.cursor/` Skillport v2 scaffold with universal agents, Email Assistant project agents, rules, hooks, and templates.

## Scope

Allowed files:
- `.cursor/**`

Do not edit:
- `app/` production code (scaffold only)

## Current observations

- No `.cursor/` directory existed before init.
- Email Assistant is local-first: Graph + YAML catalogs + Obsidian + optional Ollama.
- MVP: drafts only, no auto-send.

## Implementation steps

1. Create directory scaffold.
2. Add universal agents (architect, implementation, reviewer, test, refactor, docs, security, debugging).
3. Add project agents (graph, catalog, studio, pipeline, vault, config-json, team-config, privacy, azure).
4. Add universal and domain-specific rules.
5. Add hooks, prompts, checklists, templates.

## Tests to add/update

None — scaffold only.

## Validation commands

```bash
ls -R .cursor/
```

## Risks

- Rules may need tuning as project evolves.
- Hooks are not wired to Cursor until configured in settings.

## Rollback notes

Remove `.cursor/` directory to revert scaffold.

## Suggested commit message

Initialize Skillport v2 Cursor scaffold for Email Assistant Agent
