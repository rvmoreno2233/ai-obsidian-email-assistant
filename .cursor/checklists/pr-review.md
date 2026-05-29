# PR Review Checklist

- [ ] Scope matches plan or PR description
- [ ] No unrelated refactors
- [ ] Tests added or updated for behavior changes
- [ ] `pytest` passes
- [ ] `ruff check .` passes
- [ ] No secrets, `.env`, or tokens committed
- [ ] Catalog changes reviewed for PII (`data/catalog/`)
- [ ] MVP: no auto-send enabled without explicit approval
- [ ] Docs updated if CLI, env vars, or API changed
