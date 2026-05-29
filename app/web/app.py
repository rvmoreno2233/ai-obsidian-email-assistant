"""FastAPI application for Email Assistant catalog UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.catalog_store import (
    apply_contact_importance,
    bulk_apply_contact_importance,
    bulk_update_domains,
    filter_contacts,
    filter_domains,
    get_contacts_for_domain,
    get_domain,
    load_contacts,
    load_domains,
    save_domains,
    update_contact,
    update_domain,
)
from app.inbox_catalog import CONTACT_IMPORTANCE_LABELS, DEFAULT_EXCLUDED_CATEGORIES
from app.config import DATA_DIR, MSGRAPH_CLIENT_ID, MSAL_CACHE_PATH, PROJECT_ROOT
from app.team_config import TeamConfig, load_team_config, save_team_config, sync_hints_to_domain_categories
from app.web.jobs import JobStatus, create_job, get_job, list_jobs

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Email Assistant Studio", version="0.1.0")


class DomainPatch(BaseModel):
    category: str | None = None
    company: str | None = None
    config_client_abbrev: str | None = None
    config_client_name: str | None = None


class ContactPatch(BaseModel):
    category: str | None = None
    company: str | None = None
    importance: str | None = None
    agent_enabled: bool | None = None


class BulkContactPatch(BaseModel):
    emails: list[str]
    importance: str | None = None


class BulkDomainPatch(BaseModel):
    domains: list[str]
    category: str | None = None
    company: str | None = None


class ScrapeRequest(BaseModel):
    max_pages: int = 100
    page_size: int = 100


@app.get("/api/status")
def api_status() -> dict[str, Any]:
    domains = load_domains()
    contacts = load_contacts()
    team = load_team_config()
    return {
        "team_name": team.team_name,
        "graph_configured": bool(MSGRAPH_CLIENT_ID),
        "authenticated": MSAL_CACHE_PATH.exists(),
        "domain_count": len(domains.domains),
        "contact_count": len(contacts.contacts),
        "config_client_count": sum(1 for d in domains.domains if d.config_client_abbrev),
        "scraped_at": domains.scraped_at,
        "catalog_path": str(DATA_DIR / "catalog"),
        "vault_path": str(PROJECT_ROOT / team.vault_path),
    }


@app.get("/api/categories")
def api_categories() -> dict[str, str]:
    team = load_team_config()
    if team.categories:
        return team.categories
    from app.inbox_catalog import CATEGORY_LABELS

    return CATEGORY_LABELS


@app.get("/api/contact-importance-levels")
def api_contact_importance_levels() -> dict[str, str]:
    return CONTACT_IMPORTANCE_LABELS


@app.get("/api/team")
def api_get_team() -> TeamConfig:
    return load_team_config()


@app.put("/api/team")
def api_put_team(config: TeamConfig) -> dict[str, str]:
    save_team_config(config)
    sync_hints_to_domain_categories(config)
    return {"message": "Team config saved"}


@app.get("/api/domains")
def api_list_domains(
    search: str = "",
    category: str = "",
    sort: str = "message_count",
    desc: bool = True,
    hide_excluded: bool = True,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    catalog = load_domains()
    exclude = DEFAULT_EXCLUDED_CATEGORIES if hide_excluded and not category else None
    rows = filter_domains(
        catalog,
        search=search,
        category=category,
        sort=sort,
        desc=desc,
        exclude_categories=exclude,
    )
    start = (page - 1) * limit
    end = start + limit
    return {
        "total": len(rows),
        "page": page,
        "limit": limit,
        "items": [r.model_dump() for r in rows[start:end]],
    }


class ClientMapRequest(BaseModel):
    client_abbrev: str


@app.get("/api/config/clients")
def api_config_clients(search: str = "", limit: int = Query(50, le=200)) -> list[dict[str, Any]]:
    from app.config_json import load_clients, search_clients

    if search:
        clients = search_clients(search, limit=limit)
    else:
        clients = load_clients()[:limit]
    return [
        {
            "client_abbrev": c.client_abbrev,
            "client_name": c.client_name,
            "340b_id": c.b340_id,
            "verity_abbrev": c.verity_abbrev,
            "emr": c.emr,
            "archive_dir": c.archive_dir,
        }
        for c in clients
    ]


@app.get("/api/domains/{domain}/previews")
def api_domain_previews(domain: str, live: bool = False) -> dict[str, Any]:
    from app.catalog_store import refresh_domain_previews

    row = get_domain(domain)
    if live or not row or not row.sample_emails:
        try:
            previews = refresh_domain_previews(domain)
        except Exception as e:
            if row and row.sample_emails:
                previews = row.sample_emails
            else:
                raise HTTPException(502, str(e)) from e
    else:
        previews = row.sample_emails

    items = [p.model_dump() for p in previews] if previews else []
    if row and not items and row.sample_subjects:
        items = [{"subject": s, "body_preview": "", "sender_email": "", "message_id": ""} for s in row.sample_subjects]

    return {"domain": domain, "previews": items, "domain_row": row.model_dump() if row else None}


@app.get("/api/domains/{domain}/contacts")
def api_domain_contacts(domain: str) -> dict[str, Any]:
    row = get_domain(domain)
    if not row:
        raise HTTPException(404, f"Domain not found: {domain}")
    contacts = get_contacts_for_domain(domain)
    domain_category = row.category
    items = []
    for c in contacts:
        items.append(
            {
                **c.model_dump(),
                "importance": c.importance if c.importance in CONTACT_IMPORTANCE_LABELS else "medium",
            }
        )
    return {
        "domain": domain,
        "domain_category": domain_category,
        "contacts": items,
        "importance_labels": CONTACT_IMPORTANCE_LABELS,
    }


@app.get("/api/messages/{message_id}/preview")
def api_message_preview(message_id: str) -> dict[str, Any]:
    from app.graph_client import MsGraphBackend

    try:
        return MsGraphBackend().get_message_preview(message_id)
    except Exception as e:
        raise HTTPException(502, str(e)) from e


@app.get("/api/domains/{domain}/suggest-client")
def api_suggest_client(domain: str) -> dict[str, Any]:
    from app.catalog_store import get_domain
    from app.config_json import suggest_clients_for_text

    row = get_domain(domain)
    parts = [domain, row.company or ""] if row else [domain]
    if row:
        parts.extend(row.sample_subjects)
        for e in row.sample_emails:
            parts.append(e.subject)
            parts.append(e.body_preview)
    text = " ".join(parts)
    return {"domain": domain, "suggestions": suggest_clients_for_text(text)}


@app.post("/api/domains/{domain}/map-client")
def api_map_client(domain: str, body: ClientMapRequest) -> dict[str, Any]:
    from app.config_json import get_client_by_abbrev

    client = get_client_by_abbrev(body.client_abbrev)
    if not client:
        raise HTTPException(404, f"Client not found: {body.client_abbrev}")
    row = update_domain(
        domain,
        {
            "config_client_abbrev": client.client_abbrev,
            "config_client_name": client.client_name,
            "company": client.client_name,
            "category": "client",
        },
    )
    if not row:
        raise HTTPException(404, f"Domain not found: {domain}")
    return row.model_dump()


@app.post("/api/domains/{domain}/refresh-previews")
def api_refresh_previews(domain: str) -> dict[str, str]:
    def _task() -> dict[str, Any]:
        from app.catalog_store import refresh_domain_previews

        previews = refresh_domain_previews(domain)
        return {"message": f"Refreshed {len(previews)} previews", "count": len(previews)}

    job = create_job(f"refresh-{domain}", _task)
    return {"job_id": job.id}


@app.patch("/api/domains/{domain}")
def api_patch_domain(domain: str, patch: DomainPatch) -> dict[str, Any]:
    data = patch.model_dump(exclude_none=True)
    row = update_domain(domain, data)
    if not row:
        raise HTTPException(404, f"Domain not found: {domain}")
    return row.model_dump()


@app.post("/api/domains/bulk")
def api_bulk_domains(patch: BulkDomainPatch) -> dict[str, Any]:
    data = patch.model_dump(exclude_none=True)
    domains = data.pop("domains")
    count = bulk_update_domains(domains, data)
    return {"updated": count}


@app.get("/api/contacts")
def api_list_contacts(
    search: str = "",
    domain: str = "",
    category: str = "",
    importance: str = "",
    agent_only: bool = False,
    hide_excluded: bool = True,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    catalog = load_contacts()
    exclude = DEFAULT_EXCLUDED_CATEGORIES if hide_excluded and not category else None
    rows = filter_contacts(
        catalog,
        search=search,
        domain=domain,
        category=category,
        importance=importance,
        agent_only=agent_only,
        exclude_categories=exclude,
    )
    start = (page - 1) * limit
    end = start + limit
    items = []
    for r in rows[start:end]:
        items.append(r.model_dump())
    return {
        "total": len(rows),
        "page": page,
        "limit": limit,
        "items": items,
    }


@app.patch("/api/contacts/{email:path}")
def api_patch_contact(email: str, patch: ContactPatch) -> dict[str, Any]:
    data = patch.model_dump(exclude_none=True)
    if "importance" in data and data["importance"] in CONTACT_IMPORTANCE_LABELS:
        contact_row = next((c for c in load_contacts().contacts if c.email.lower() == email.lower()), None)
        if not contact_row:
            raise HTTPException(404, f"Contact not found: {email}")
        domain_row = get_domain(contact_row.domain)
        domain_category = domain_row.category if domain_row else contact_row.category
        row = apply_contact_importance(email, data.pop("importance"), domain_category)
        if not row:
            raise HTTPException(404, f"Contact not found: {email}")
        if data:
            row = update_contact(email, data)
        return row.model_dump() if row else {}
    row = update_contact(email, data)
    if not row:
        raise HTTPException(404, f"Contact not found: {email}")
    return row.model_dump()


@app.post("/api/contacts/bulk")
def api_bulk_contacts(patch: BulkContactPatch) -> dict[str, Any]:
    if not patch.importance or patch.importance not in CONTACT_IMPORTANCE_LABELS:
        raise HTTPException(400, "importance required (high, medium, low)")
    count = bulk_apply_contact_importance(patch.emails, patch.importance)
    return {"updated": count}


@app.patch("/api/contacts/{email:path}/importance")
def api_patch_contact_importance(email: str, patch: ContactPatch) -> dict[str, Any]:
    if not patch.importance or patch.importance not in CONTACT_IMPORTANCE_LABELS:
        raise HTTPException(400, "importance required (high, medium, low)")
    contact_row = next((c for c in load_contacts().contacts if c.email.lower() == email.lower()), None)
    if not contact_row:
        raise HTTPException(404, f"Contact not found: {email}")
    domain_row = get_domain(contact_row.domain)
    domain_category = domain_row.category if domain_row else contact_row.category
    row = apply_contact_importance(email, patch.importance, domain_category)
    if not row:
        raise HTTPException(404, f"Contact not found: {email}")
    return row.model_dump()


@app.post("/api/actions/scrape")
def api_scrape(req: ScrapeRequest) -> dict[str, str]:
    def _task() -> dict[str, Any]:
        from app.inbox_catalog import save_catalog, scrape_inbox

        domains, contacts = scrape_inbox(max_pages=req.max_pages, page_size=req.page_size)
        save_catalog(domains, contacts)
        return {
            "message": f"Scraped {sum(d.message_count for d in domains)} messages",
            "domains": len(domains),
            "contacts": len(contacts),
        }

    job = create_job("scrape-inbox", _task)
    return {"job_id": job.id}


@app.post("/api/actions/categorize")
def api_categorize() -> dict[str, str]:
    def _task() -> dict[str, Any]:
        from app.catalog_categorize import categorize_domains

        n = categorize_domains()
        return {"message": f"Updated {n} domains", "updated": n}

    job = create_job("categorize", _task)
    return {"job_id": job.id}


@app.post("/api/actions/apply")
def api_apply() -> dict[str, str]:
    def _task() -> dict[str, Any]:
        from app.catalog_apply import apply_catalog
        from app.catalog_categorize import categorize_domains

        categorize_domains()
        stats = apply_catalog()
        return {"message": "Catalog applied to vault and agents", **stats}

    job = create_job("apply-catalog", _task)
    return {"job_id": job.id}


@app.get("/api/jobs")
def api_jobs() -> list[dict[str, Any]]:
    return [
        {
            "id": j.id,
            "name": j.name,
            "status": j.status.value,
            "message": j.message,
            "created_at": j.created_at,
            "finished_at": j.finished_at,
            "error": j.error,
            "result": j.result,
        }
        for j in list_jobs()
    ]


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "id": job.id,
        "name": job.name,
        "status": job.status.value,
        "message": job.message,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
        "error": job.error,
        "result": job.result,
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
