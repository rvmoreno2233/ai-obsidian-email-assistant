# Plans Directory

Durable task memory for agent sessions. When a chat gets stale, save state here and start fresh.

## Structure

- `active/` — current work in progress
- `completed/` — finished phases (move from active when done)
- `archived/` — old or abandoned plans

## Usage

1. Architect agent creates a plan in `active/`.
2. Implementation agent references the plan file.
3. On completion, move to `completed/`.

## Naming

`phase<number>-<slug>.md` — e.g. `phase1-catalog-apply.md`
