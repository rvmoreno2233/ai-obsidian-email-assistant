# Agent Setup Guide

#email-assistant

## What was scraped

From your inbox (10,000 most recent messages):

| Category | Domain | Messages |
|----------|--------|----------|
| Internal | `creocomp.com` | ~3,826 |
| 340B vendor | `capturerx.com` | ~522 |
| 340B vendor | `verity340b.com` + `account.i340b.com` | ~657 |
| 340B vendor | `cervey.com` | (see catalog) |
| Wholesaler | `cardinalhealth.com` | (see catalog) |
| Wholesaler | `cvshealth.com` | ~131 |

Full list: `data/catalog/inbox_domains.yaml`  
Contacts ranked: `data/catalog/inbox_contacts.yaml`

## Your job: categorize domains

Open `data/catalog/inbox_domains.yaml` and set `category` for each domain:

```yaml
category: 340b_vendor   # CaptureRx, Verity, Cervey
category: pharmacy      # retail, specialty, mail-order pharmacies
category: wholesaler    # Cardinal, CVS distribution
category: internal      # Creo
category: client        # covered entities / clinics
category: partner       # Techvera, ModMed, etc.
category: newsletter    # noreply, marketing
category: ignore        # training, noise
```

Hints file: `data/domain_categories.yaml`

Then re-apply:

```bash
email-assistant apply-catalog
```

## Agent policies

Top contacts get policies in `agents/contacts/*.policy.md`  
Linked from `vault/Contacts/` notes.

Toggle per contact in `inbox_contacts.yaml`:

```yaml
agent_enabled: true
importance: high
```

## Scrape more history

```bash
email-assistant scrape-inbox --max-pages 200   # up to 20k messages
email-assistant categorize-domains
email-assistant apply-catalog
```

## Back to

[[Home]] · [[Email Assistant/Domain Catalog]]
