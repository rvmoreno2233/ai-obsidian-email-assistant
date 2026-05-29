"""Persistent JSONL queue store for approval, auto, and log pipelines."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from app.config import QUEUE_DIR

QueueName = Literal["approval", "auto", "log"]
QueueStatus = Literal["pending", "approved", "rejected", "sent"]


class QueueEntry(BaseModel):
    """Single item in the approval or auto response queue."""

    id: str
    created_at: str
    message_id: str
    rule_id: str
    template_id: str
    subject: str
    body: str
    status: QueueStatus = "pending"
    thread_note: str = ""
    draft_id: str | None = None


class PollerState(BaseModel):
    """Cursor and stats for the background inbox poller."""

    enabled: bool = False
    interval_seconds: int = 300
    last_run: str | None = None
    last_processed_message_id: str | None = None
    last_processed_count: int = 0


class ResponseQueueStore:
    """Thread-safe JSONL queue store with an in-memory mirror."""

    _QUEUE_FILES: dict[QueueName, str] = {
        "approval": "approval.jsonl",
        "auto": "auto.jsonl",
        "log": "log.jsonl",
    }

    def __init__(self, queue_dir: Path | None = None) -> None:
        self.queue_dir = queue_dir or QUEUE_DIR
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._mirror: dict[QueueName, list[dict[str, Any]]] = {
            "approval": [],
            "auto": [],
            "log": [],
        }
        self.reload()

    def _queue_path(self, queue: QueueName) -> Path:
        return self.queue_dir / self._QUEUE_FILES[queue]

    def _poller_state_path(self) -> Path:
        return self.queue_dir / "poller_state.json"

    def reload(self) -> None:
        """Reload all queues from disk into the in-memory mirror."""
        with self._lock:
            for queue in self._QUEUE_FILES:
                path = self._queue_path(queue)
                rows: list[dict[str, Any]] = []
                if path.exists():
                    for line in path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if line:
                            rows.append(json.loads(line))
                self._mirror[queue] = rows

    def _append_row(self, queue: QueueName, row: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            path = self._queue_path(queue)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            self._mirror[queue].append(row)
            return row

    @staticmethod
    def new_entry_id() -> str:
        """Generate a unique queue entry id."""
        return f"q_{uuid.uuid4().hex[:12]}"

    @staticmethod
    def utc_now() -> str:
        return datetime.now(UTC).isoformat()

    def append_entry(self, queue: QueueName, entry: QueueEntry) -> QueueEntry:
        """Append a structured queue entry to approval or auto queue."""
        if queue == "log":
            msg = "Use append_log() for the log queue"
            raise ValueError(msg)
        return QueueEntry.model_validate(self._append_row(queue, entry.model_dump()))

    def append_log(self, record: dict[str, Any]) -> dict[str, Any]:
        """Append a raw log record (e.g. matched email metadata)."""
        if "logged_at" not in record:
            record = {**record, "logged_at": self.utc_now()}
        return self._append_row("log", record)

    def list_entries(self, queue: QueueName) -> list[QueueEntry]:
        """Return approval or auto queue entries from the in-memory mirror."""
        if queue == "log":
            msg = "Use list_log() for the log queue"
            raise ValueError(msg)
        with self._lock:
            return [QueueEntry.model_validate(row) for row in self._mirror[queue]]

    def list_log(self) -> list[dict[str, Any]]:
        """Return log queue records from the in-memory mirror."""
        with self._lock:
            return list(self._mirror["log"])

    def update_status(
        self,
        queue: QueueName,
        entry_id: str,
        status: QueueStatus,
    ) -> QueueEntry | None:
        """Update status for an approval/auto entry in JSONL and mirror."""
        if queue == "log":
            msg = "Log queue entries are append-only"
            raise ValueError(msg)

        with self._lock:
            rows = self._mirror[queue]
            updated: dict[str, Any] | None = None
            for index, row in enumerate(rows):
                if row.get("id") == entry_id:
                    row["status"] = status
                    rows[index] = row
                    updated = row
                    break

            if updated is None:
                return None

            path = self._queue_path(queue)
            with path.open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")

            return QueueEntry.model_validate(updated)

    def load_poller_state(self) -> PollerState:
        """Load poller cursor/state from disk."""
        path = self._poller_state_path()
        if not path.exists():
            return PollerState()
        raw = json.loads(path.read_text(encoding="utf-8"))
        return PollerState.model_validate(raw)

    def save_poller_state(self, state: PollerState) -> None:
        """Persist poller cursor/state to disk."""
        path = self._poller_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
