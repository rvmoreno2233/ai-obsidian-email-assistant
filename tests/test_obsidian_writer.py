"""Tests for ObsidianWriter."""

import json
from pathlib import Path

from app.classifier import RuleBasedClassifier
from app.config import DATA_DIR, FIXTURES_DIR
from app.entity_matcher import load_catalogs, match_entities
from app.obsidian_writer import ObsidianWriter
from app.responder import RuleBasedResponder
from app.schemas import NormalizedEmail


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

    assert any("Companies" in w for w in written)
    company_note = tmp_vault / "Companies" / "Acme Health.md"
    assert company_note.exists()
    content = company_note.read_text()
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
    assert "status: closed" in yaml_data or 'status: closed' in yaml_data
