"""Tests for JSONL response queue persistence."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.response_queue import PollerState, QueueEntry, ResponseQueueStore


def _sample_entry(entry_id: str = "q_test001") -> QueueEntry:
    return QueueEntry(
        id=entry_id,
        created_at="2026-05-29T12:00:00+00:00",
        message_id="msg-1",
        rule_id="capturerx_ack",
        template_id="ack_template",
        subject="Re: CaptureRx ticket",
        body="Thanks for your email.",
        status="pending",
        thread_note="Email Assistant/Threads/example.md",
    )


def test_append_and_list_entries(tmp_queue_dir: Path):
    store = ResponseQueueStore(tmp_queue_dir)
    entry = _sample_entry()
    store.append_entry("approval", entry)

    items = store.list_entries("approval")
    assert len(items) == 1
    assert items[0].id == entry.id
    assert items[0].status == "pending"


def test_update_status_persists_across_reload(tmp_queue_dir: Path):
    store = ResponseQueueStore(tmp_queue_dir)
    entry = _sample_entry("q_persist01")
    store.append_entry("approval", entry)

    updated = store.update_status("approval", entry.id, "approved")
    assert updated is not None
    assert updated.status == "approved"

    reloaded = ResponseQueueStore(tmp_queue_dir)
    items = reloaded.list_entries("approval")
    assert len(items) == 1
    assert items[0].status == "approved"


def test_append_log_and_mirror(tmp_queue_dir: Path):
    store = ResponseQueueStore(tmp_queue_dir)
    record = {"message_id": "msg-log-1", "rule_id": "capturerx_ack"}
    store.append_log(record)

    logs = store.list_log()
    assert len(logs) == 1
    assert logs[0]["message_id"] == "msg-log-1"
    assert "logged_at" in logs[0]

    reloaded = ResponseQueueStore(tmp_queue_dir)
    assert len(reloaded.list_log()) == 1


def test_poller_state_round_trip(tmp_queue_dir: Path):
    store = ResponseQueueStore(tmp_queue_dir)
    state = PollerState(
        enabled=True,
        interval_seconds=120,
        last_run="2026-05-29T12:00:00+00:00",
        last_processed_message_id="msg-cursor",
        last_processed_count=5,
    )
    store.save_poller_state(state)

    reloaded = ResponseQueueStore(tmp_queue_dir)
    loaded = reloaded.load_poller_state()
    assert loaded.enabled is True
    assert loaded.interval_seconds == 120
    assert loaded.last_processed_message_id == "msg-cursor"
    assert loaded.last_processed_count == 5


def test_thread_safe_concurrent_appends(tmp_queue_dir: Path):
    store = ResponseQueueStore(tmp_queue_dir)

    def append_one(index: int) -> None:
        entry = _sample_entry(f"q_thread_{index:03d}")
        store.append_entry("auto", entry)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(append_one, range(20)))

    items = store.list_entries("auto")
    assert len(items) == 20
    ids = {item.id for item in items}
    assert len(ids) == 20

    reloaded = ResponseQueueStore(tmp_queue_dir)
    assert len(reloaded.list_entries("auto")) == 20
