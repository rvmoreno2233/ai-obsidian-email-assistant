"""Tests for action router."""

import json
from pathlib import Path

from app.action_router import ActionRouter
from app.classifier import RuleBasedClassifier
from app.config import DATA_DIR, FIXTURES_DIR
from app.entity_matcher import load_catalogs, match_entities
from app.graph_client import MockGraphBackend
from app.obsidian_writer import ObsidianWriter
from app.responder import RuleBasedResponder
from app.schemas import NormalizedEmail


def test_route_creates_draft_and_notes(tmp_path: Path, data_dir: Path):
    raw = json.loads((FIXTURES_DIR / "sample_emails.json").read_text())
    email = NormalizedEmail.model_validate(
        next(e for e in raw if e["message_id"] == "msg-needs-response")
    )
    catalogs = load_catalogs(data_dir)
    clf = RuleBasedClassifier(catalogs)
    entities = match_entities(email, catalogs)
    classification = clf.classify(email, entities)
    draft = RuleBasedResponder().draft(email, classification)

    writer = ObsidianWriter(tmp_path, data_dir=data_dir)
    router = ActionRouter(writer=writer, backend=MockGraphBackend())
    action = router.route(email, classification, draft)

    assert action.draft_created is True
    assert len(action.notes_written) > 0
