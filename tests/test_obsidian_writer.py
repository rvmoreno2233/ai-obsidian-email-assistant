"""Tests for ObsidianWriter."""

import json
from pathlib import Path

from app.classifier import RuleBasedClassifier
from app.config import FIXTURES_DIR
from app.entity_matcher import load_catalogs, match_entities
from app.obsidian_writer import ObsidianWriter, normalize_subject_root, thread_slug
from app.responder import RuleBasedResponder
from app.schemas import DraftResponse, EmailClassification, NormalizedEmail


def test_write_email_summary_creates_files(tmp_vault: Path, data_dir: Path):
    raw = json.loads((FIXTURES_DIR / "sample_emails.json").read_text())
    email = NormalizedEmail.model_validate(
        next(e for e in raw if e["message_id"] == "msg-schema-approval")
    )
    catalogs = load_catalogs(data_dir)
    clf = RuleBasedClassifier(catalogs)
    entities = match_entities(email, catalogs)
    classification = clf.classify(email, entities)
    responder = RuleBasedResponder()
    draft = responder.draft(email, classification)

    writer = ObsidianWriter(tmp_vault, data_dir=data_dir)
    written = writer.write_email_summary(email, classification, draft)

    assert any("Contacts" in w or "Inbox Review" in w for w in written)
    contact_note = tmp_vault / "Contacts" / "Jane Doe.md"
    assert contact_note.exists()
    content = contact_note.read_text()
    assert "waiting_info_arrived" in content or "schema" in content.lower()
    assert "[[Jane Doe]]" in content or "Jane Doe" in content


def test_mark_waiting_item_complete(tmp_vault: Path, data_dir: Path, monkeypatch):
    monkeypatch.setattr("app.obsidian_writer.UPDATE_WAITING_YAML", True)
    writer = ObsidianWriter(tmp_vault, data_dir=data_dir)
    writer.mark_waiting_item_complete("acme_schema_approval", "schema approved in email")

    waiting_note = tmp_vault / "Email Assistant" / "Waiting For.md"
    assert waiting_note.exists()
    assert "acme_schema_approval" in waiting_note.read_text()

    yaml_data = (data_dir / "waiting_for.yaml").read_text()
    assert "status: closed" in yaml_data or "status: closed" in yaml_data


def test_thread_slug_from_domain_and_subject_root():
    email = NormalizedEmail(
        message_id="msg-1",
        subject="Re: Fwd: CaptureRx ticket #42",
        sender_name="Jane",
        sender_email="jane@acmehealth.com",
        received_at="2026-05-29T10:00:00Z",
        body_text="Please review.",
    )
    assert normalize_subject_root(email.subject) == "CaptureRx ticket #42"
    assert thread_slug(email) == "acmehealth.com--capturerx-ticket-42"


def test_append_to_thread_creates_slug_file(tmp_vault: Path, data_dir: Path):
    email = NormalizedEmail(
        message_id="msg-thread-1",
        subject="Re: Weekly update",
        sender_name="Jane Doe",
        sender_email="jane@acmehealth.com",
        received_at="2026-05-29T10:00:00Z",
        body_text="Status attached.",
    )
    classification = EmailClassification(
        category="project_update",
        priority="medium",
        confidence=0.9,
        company="Acme Health",
        contact="Jane Doe",
        summary="Weekly project status.",
        reason="Matched project keywords.",
        needs_human_review=False,
    )
    draft = DraftResponse(
        should_reply=True,
        subject="Re: Weekly update",
        body="Thanks, received.",
        reason="Rule matched.",
    )

    writer = ObsidianWriter(tmp_vault, data_dir=data_dir)
    rel_path = writer.append_to_thread(email, classification, draft)

    assert rel_path.startswith("Email Assistant/Threads/")
    note_path = tmp_vault / rel_path
    assert note_path.exists()
    content = note_path.read_text()
    assert "Weekly update" in content
    assert "Thanks, received." in content
    assert thread_slug(email) in note_path.stem


def test_append_to_thread_appends_same_slug(tmp_vault: Path, data_dir: Path):
    base = dict(
        sender_name="Jane Doe",
        sender_email="jane@acmehealth.com",
        received_at="2026-05-29T11:00:00Z",
        body_text="Follow-up.",
    )
    email1 = NormalizedEmail(
        message_id="msg-thread-2a",
        subject="Re: Weekly update",
        **base,
    )
    email2 = NormalizedEmail(
        message_id="msg-thread-2b",
        subject="Fwd: Re: Weekly update",
        **base,
    )
    classification = EmailClassification(
        category="project_update",
        priority="medium",
        confidence=0.9,
        summary="Follow-up message.",
        reason="Rule matched.",
        needs_human_review=False,
    )

    writer = ObsidianWriter(tmp_vault, data_dir=data_dir)
    path1 = writer.append_to_thread(email1, classification)
    path2 = writer.append_to_thread(email2, classification)

    assert path1 == path2
    content = (tmp_vault / path1).read_text()
    assert content.count("### 2026-05-29") == 2
