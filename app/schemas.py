"""Pydantic models for structured email assistant data."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

EmailCategory = Literal[
    "needs_response",
    "waiting_info_arrived",
    "fyi",
    "newsletter",
    "invoice_or_admin",
    "meeting_request",
    "project_update",
    "ignore_low_priority",
]

Priority = Literal["low", "medium", "high", "urgent"]


class NormalizedEmail(BaseModel):
    """Canonical representation of an email for processing."""

    message_id: str
    subject: str
    sender_name: Optional[str] = None
    sender_email: str
    received_at: str
    body_text: str
    web_link: Optional[str] = None


class EmailClassification(BaseModel):
    """Classifier output for a single email."""

    category: EmailCategory
    priority: Priority
    confidence: float = Field(ge=0, le=1)
    company: Optional[str] = None
    contact: Optional[str] = None
    project: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    summary: str
    reason: str
    needs_human_review: bool = True


class WaitingItemMatch(BaseModel):
    """Match between an email and an open waiting-for item."""

    waiting_item_id: str
    project: Optional[str] = None
    matched: bool
    evidence: str
    confidence: float = Field(ge=0, le=1)


class DraftResponse(BaseModel):
    """Suggested reply draft (never auto-sent in MVP)."""

    should_reply: bool
    auto_send_allowed: bool = False
    subject: Optional[str] = None
    body: Optional[str] = None
    reason: str


class RoutedAction(BaseModel):
    """Record of actions taken for an email."""

    message_id: str
    notes_written: list[str] = Field(default_factory=list)
    draft_created: bool = False
    draft_location: Optional[str] = None
    notifications: list[str] = Field(default_factory=list)
    waiting_items_closed: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    rule_matched: bool = False
    rule_id: Optional[str] = None
    queue_entry_id: Optional[str] = None


# --- YAML catalog models ---


class CompanyRecord(BaseModel):
    name: str
    domains: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    default_project: Optional[str] = None
    contacts: list[str] = Field(default_factory=list)


class ContactRecord(BaseModel):
    name: str
    email: str
    company: Optional[str] = None
    role: Optional[str] = None
    importance: Literal["low", "medium", "high"] = "medium"
    notes: list[str] = Field(default_factory=list)


class ProjectRecord(BaseModel):
    name: str
    company: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    notification_level: Literal["low", "medium", "high"] = "medium"


class WaitingItem(BaseModel):
    id: str
    project: Optional[str] = None
    company: Optional[str] = None
    waiting_for: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    notify_when_found: bool = True
    status: Literal["open", "closed"] = "open"


class CompaniesCatalog(BaseModel):
    companies: list[CompanyRecord] = Field(default_factory=list)


class ContactsCatalog(BaseModel):
    contacts: list[ContactRecord] = Field(default_factory=list)


class ProjectsCatalog(BaseModel):
    projects: list[ProjectRecord] = Field(default_factory=list)


class WaitingForCatalog(BaseModel):
    waiting_for: list[WaitingItem] = Field(default_factory=list)


class EntityMatchResult(BaseModel):
    """Aggregated entity matching for one email."""

    company: Optional[str] = None
    contact: Optional[str] = None
    projects: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    waiting_matches: list[WaitingItemMatch] = Field(default_factory=list)
