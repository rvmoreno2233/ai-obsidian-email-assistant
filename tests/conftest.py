"""Shared pytest fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import FIXTURES_DIR
from app.schemas import NormalizedEmail

FIXTURE_EMAILS_PATH = FIXTURES_DIR / "sample_emails.json"
FIXTURE_CATALOG_DIR = FIXTURES_DIR / "catalog"


@pytest.fixture
def sample_emails() -> list[NormalizedEmail]:
    if not FIXTURE_EMAILS_PATH.exists():
        return []
    raw = json.loads(FIXTURE_EMAILS_PATH.read_text(encoding="utf-8"))
    return [NormalizedEmail.model_validate(e) for e in raw]


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """Temporary Obsidian vault root."""
    for folder in ("Companies", "Contacts", "Projects", "Email Assistant"):
        (tmp_path / folder).mkdir(parents=True)
    return tmp_path


@pytest.fixture
def fixture_catalog_dir() -> Path:
    """Synthetic YAML catalogs for deterministic matcher tests."""
    return FIXTURE_CATALOG_DIR


@pytest.fixture
def data_dir(tmp_path: Path, fixture_catalog_dir: Path) -> Path:
    """Copy synthetic fixture catalogs into a temp data dir."""
    dest = tmp_path / "data"
    dest.mkdir()
    for name in ("companies.yaml", "contacts.yaml", "projects.yaml", "waiting_for.yaml"):
        src = fixture_catalog_dir / name
        if src.exists():
            (dest / name).write_text(src.read_text(encoding="utf-8"))
    return dest


@pytest.fixture
def tmp_queue_dir(tmp_path: Path) -> Path:
    """Temporary queue directory for response queue tests."""
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir()
    return queue_dir
