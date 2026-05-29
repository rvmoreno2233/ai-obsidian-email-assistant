# Inbox catalog (local scrape output)

This directory is populated by `email-assistant scrape-inbox` and contains **PII** (sender addresses, subjects, previews).

- **Not committed to git** — see root `.gitignore`
- After scrape: review and categorize via Studio or CLI
- Apply merges into `data/companies.yaml`, `data/contacts.yaml`, vault, and agents

To bootstrap locally:

```bash
cp config.json.example config.json   # if needed
email-assistant scrape-inbox
```
