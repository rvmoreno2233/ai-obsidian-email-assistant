"""FastAPI application for Email Assistant catalog UI."""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
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
    update_contact,
    update_domain,
)
from app.config import DATA_DIR, MSAL_CACHE_PATH, MSGRAPH_CLIENT_ID, PROJECT_ROOT, PROMPTS_DIR
from app.email_rules import (
    EmailRule,
    ResponseTemplate,
    add_rule,
    add_template,
    delete_rule,
    delete_template,
    load_rules,
    load_templates,
    update_rule,
    update_template,
)
from app.inbox_catalog import CONTACT_IMPORTANCE_LABELS, DEFAULT_EXCLUDED_CATEGORIES
from app.llm_client import LLMConnectionError, OllamaClient
from app.response_queue import ResponseQueueStore
from app.team_config import (
    TeamConfig,
    load_team_config,
    save_team_config,
    sync_hints_to_domain_categories,
)
from app.web.jobs import create_job, get_job, list_jobs
from app.web.poller import BackgroundPoller

STATIC_DIR = Path(__file__).parent / "static"

_queue_store = ResponseQueueStore()
_poller = BackgroundPoller(queue_store=_queue_store)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    await _poller.start()
    yield
    await _poller.stop()


app = FastAPI(title="Email Assistant Studio", version="0.1.0", lifespan=_lifespan)


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
        items = [
            {"subject": s, "body_preview": "", "sender_email": "", "message_id": ""}
            for s in row.sample_subjects
        ]

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
                "importance": (
                    c.importance if c.importance in CONTACT_IMPORTANCE_LABELS else "medium"
                ),
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
        contact_row = next(
            (c for c in load_contacts().contacts if c.email.lower() == email.lower()), None
        )
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
    contact_row = next(
        (c for c in load_contacts().contacts if c.email.lower() == email.lower()), None
    )
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


# --- Email Settings: Ollama ---


@app.get("/api/ollama/health")
def api_ollama_health() -> dict[str, Any]:
    return OllamaClient().health_check()


class OllamaTestRequest(BaseModel):
    prompt: str = "Reply with exactly: ok"


@app.post("/api/ollama/test")
def api_ollama_test(body: OllamaTestRequest) -> dict[str, Any]:
    client = OllamaClient()
    started = time.perf_counter()
    try:
        reply = client.chat_text(messages=[{"role": "user", "content": body.prompt}])
    except LLMConnectionError as exc:
        raise HTTPException(503, str(exc)) from exc
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    return {"ok": True, "latency_ms": elapsed_ms, "reply": reply[:500]}


# --- Email Settings: Templates ---


class TemplateCreate(BaseModel):
    name: str
    subject_prefix: str = "Re: "
    body: str = ""
    ai_instructions: str = ""
    created_by: str = "manual"


class TemplatePatch(BaseModel):
    name: str | None = None
    subject_prefix: str | None = None
    body: str | None = None
    ai_instructions: str | None = None
    created_by: str | None = None


class TemplateAiAssistRequest(BaseModel):
    description: str
    team_name: str | None = None


@app.get("/api/templates")
def api_list_templates() -> dict[str, Any]:
    catalog = load_templates()
    return {"items": [t.model_dump() for t in catalog.templates]}


@app.post("/api/templates")
def api_create_template(body: TemplateCreate) -> dict[str, Any]:
    template_id = f"tpl_{uuid.uuid4().hex[:10]}"
    template = ResponseTemplate(id=template_id, **body.model_dump())
    try:
        add_template(template)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return template.model_dump()


@app.patch("/api/templates/{template_id}")
def api_patch_template(template_id: str, patch: TemplatePatch) -> dict[str, Any]:
    data = patch.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "No fields to update")
    updated = update_template(template_id, data)
    if not updated:
        raise HTTPException(404, f"Template not found: {template_id}")
    return updated.model_dump()


@app.delete("/api/templates/{template_id}")
def api_delete_template(template_id: str) -> dict[str, str]:
    if not delete_template(template_id):
        raise HTTPException(404, f"Template not found: {template_id}")
    return {"message": "Template deleted"}


@app.post("/api/templates/ai-assist")
def api_template_ai_assist(body: TemplateAiAssistRequest) -> dict[str, str]:
    team = body.team_name or load_team_config().team_name
    prompt_path = PROMPTS_DIR / "template_assist.md"
    prompt = prompt_path.read_text(encoding="utf-8")
    prompt = prompt.replace("{description}", body.description)
    prompt = prompt.replace("{team_name}", team)
    client = OllamaClient()
    try:
        body_text = client.chat_text(messages=[{"role": "user", "content": prompt}])
    except LLMConnectionError as exc:
        raise HTTPException(503, str(exc)) from exc

    ai_instructions = ""
    if "AI instructions:" in body_text:
        main, _, tail = body_text.partition("AI instructions:")
        body_text = main.strip()
        ai_instructions = tail.strip()
    return {"body": body_text, "ai_instructions": ai_instructions}


# --- Email Settings: Rules ---


class RuleCreate(BaseModel):
    name: str
    enabled: bool = True
    match: dict[str, Any] = Field(default_factory=dict)
    template_id: str
    generation: str = "canned"
    delivery: str = "approval"
    append_to_existing_note: bool = True


class RulePatch(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    match: dict[str, Any] | None = None
    template_id: str | None = None
    generation: str | None = None
    delivery: str | None = None
    append_to_existing_note: bool | None = None


@app.get("/api/rules")
def api_list_rules() -> dict[str, Any]:
    catalog = load_rules()
    return {"items": [r.model_dump() for r in catalog.rules]}


@app.post("/api/rules")
def api_create_rule(body: RuleCreate) -> dict[str, Any]:
    rule_id = f"rule_{uuid.uuid4().hex[:10]}"
    payload = body.model_dump()
    match_data = payload.pop("match", {})
    rule = EmailRule(id=rule_id, match=match_data, **payload)
    try:
        add_rule(rule)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return rule.model_dump()


@app.patch("/api/rules/{rule_id}")
def api_patch_rule(rule_id: str, patch: RulePatch) -> dict[str, Any]:
    data = patch.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "No fields to update")
    updated = update_rule(rule_id, data)
    if not updated:
        raise HTTPException(404, f"Rule not found: {rule_id}")
    return updated.model_dump()


@app.delete("/api/rules/{rule_id}")
def api_delete_rule(rule_id: str) -> dict[str, str]:
    if not delete_rule(rule_id):
        raise HTTPException(404, f"Rule not found: {rule_id}")
    return {"message": "Rule deleted"}


# --- Email Settings: Poller & process-now ---


class PollerPatch(BaseModel):
    enabled: bool | None = None
    interval_seconds: int | None = Field(default=None, ge=30, le=86400)


@app.get("/api/email-settings/poller")
def api_get_poller() -> dict[str, Any]:
    return _poller.get_state().model_dump()


@app.put("/api/email-settings/poller")
def api_put_poller(patch: PollerPatch) -> dict[str, Any]:
    state = _poller.get_state()
    data = patch.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "No fields to update")
    updated = state.model_copy(update=data)
    _poller.save_state(updated)
    return updated.model_dump()


class ProcessNowRequest(BaseModel):
    top: int = Field(default=25, ge=1, le=200)


@app.post("/api/email-settings/process-now")
def api_process_now(req: ProcessNowRequest) -> dict[str, str]:
    def _task() -> dict[str, Any]:
        from app.inbox_processor import process_inbox

        state = _poller.get_state()
        result = process_inbox(top=req.top, since_message_id=state.last_processed_message_id)
        state.last_run = _queue_store.utc_now()
        state.last_processed_count = result.processed
        if result.last_message_id:
            state.last_processed_message_id = result.last_message_id
        _poller.save_state(state)
        payload = result.as_dict()
        payload["message"] = f"Processed {result.processed} email(s)"
        return payload

    job = create_job("process-inbox", _task)
    return {"job_id": job.id}


# --- Email Settings: Queues ---


@app.get("/api/queue/approval")
def api_queue_approval(status: str = "") -> dict[str, Any]:
    items = _queue_store.list_entries("approval")
    if status:
        items = [item for item in items if item.status == status]
    return {"items": [item.model_dump() for item in items]}


@app.post("/api/queue/approval/{entry_id}/approve")
def api_queue_approve(entry_id: str) -> dict[str, Any]:
    updated = _queue_store.update_status("approval", entry_id, "approved")
    if not updated:
        raise HTTPException(404, f"Queue entry not found: {entry_id}")
    return updated.model_dump()


@app.post("/api/queue/approval/{entry_id}/reject")
def api_queue_reject(entry_id: str) -> dict[str, Any]:
    updated = _queue_store.update_status("approval", entry_id, "rejected")
    if not updated:
        raise HTTPException(404, f"Queue entry not found: {entry_id}")
    return updated.model_dump()


@app.get("/api/queue/auto")
def api_queue_auto() -> dict[str, Any]:
    items = _queue_store.list_entries("auto")
    return {"items": [item.model_dump() for item in items]}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
