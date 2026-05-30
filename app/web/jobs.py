"""Background job runner for long-running UI actions."""

from __future__ import annotations

import threading
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    name: str
    status: JobStatus = JobStatus.PENDING
    created_at: str = ""
    finished_at: str = ""
    message: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""


_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def create_job(name: str, fn: Callable[[], dict[str, Any]]) -> Job:
    job = Job(
        id=uuid.uuid4().hex[:12],
        name=name,
        created_at=datetime.now(UTC).isoformat(),
    )
    with _lock:
        _jobs[job.id] = job

    def _run() -> None:
        with _lock:
            job.status = JobStatus.RUNNING
        try:
            result = fn()
            with _lock:
                job.status = JobStatus.COMPLETED
                job.result = result
                job.message = result.get("message", "Done")
        except Exception as e:
            with _lock:
                job.status = JobStatus.FAILED
                job.error = str(e)
                job.message = str(e)
                job.result = {"traceback": traceback.format_exc()}
        finally:
            with _lock:
                job.finished_at = datetime.now(UTC).isoformat()

    threading.Thread(target=_run, daemon=True).start()
    return job


def get_job(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)


def list_jobs(limit: int = 20) -> list[Job]:
    with _lock:
        jobs = sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)
    return jobs[:limit]
