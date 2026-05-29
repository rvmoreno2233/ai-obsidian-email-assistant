# Obsidian Vault (in-repo)

This folder is the **Obsidian vault** for the Email Assistant Agent. Open it directly in Obsidian:

1. Obsidian → **Open folder as vault**
2. Select this directory: `Email_Agent/vault`

## Layout

```
vault/
├── Home.md                 ← start here (pin this note)
├── Companies/
├── Contacts/
├── Projects/
├── Email Assistant/        ← agent triage dashboards
├── templates/              ← Obsidian templates for manual notes
└── .obsidian/              ← vault settings (sync-friendly subset)
```

## Sync later

Because the vault is inside the Git repo, you can:

- **Git** — commit note changes with code (agent appends are diff-friendly)
- **Obsidian Sync** — point sync at this `vault/` folder only
- **iCloud / Dropbox** — sync the whole repo or just `vault/`

Do **not** commit `.obsidian/workspace.json` (window layout; already gitignored).

## Agent integration

Set in repo root `.env`:

```bash
OBSIDIAN_VAULT_PATH=/absolute/path/to/Email_Agent/vault
```

Or omit it — the agent defaults to `./vault` relative to the project root.

Machine-readable catalogs stay in `../data/*.yaml`. Edit YAML for matching rules; use Obsidian for narrative context and email history.
