"""Background asyncio poller for periodic inbox processing."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import POLLER_INTERVAL_SECONDS
from app.inbox_processor import process_inbox
from app.response_queue import PollerState, ResponseQueueStore

logger = logging.getLogger(__name__)


class BackgroundPoller:
    """Run ``process_inbox`` on an interval; persist cursor in poller_state.json."""

    def __init__(
        self,
        queue_store: ResponseQueueStore | None = None,
        interval_seconds: int | None = None,
    ) -> None:
        self.queue_store = queue_store or ResponseQueueStore()
        self._default_interval = interval_seconds or POLLER_INTERVAL_SECONDS
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    def get_state(self) -> PollerState:
        state = self.queue_store.load_poller_state()
        if state.interval_seconds <= 0:
            state.interval_seconds = self._default_interval
        return state

    def save_state(self, state: PollerState) -> None:
        self.queue_store.save_poller_state(state)

    async def start(self) -> None:
        """Start the background polling loop if not already running."""
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="email-assistant-poller")
        logger.info("Background poller started")

    async def stop(self) -> None:
        """Signal the loop to stop and wait for the task to finish."""
        self._stop_event.set()
        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=10.0)
            except TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
        self._task = None
        logger.info("Background poller stopped")

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            state = self.get_state()
            if state.enabled:
                try:
                    await asyncio.to_thread(self._tick, state)
                except Exception:
                    logger.exception("Poller tick failed")

            interval = max(1, self.get_state().interval_seconds)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except TimeoutError:
                continue

    def _tick(self, state: PollerState) -> dict[str, Any]:
        """Run one poller cycle (blocking; call from thread)."""
        result = process_inbox(since_message_id=state.last_processed_message_id)
        state.last_run = self.queue_store.utc_now()
        state.last_processed_count = result.processed
        if result.last_message_id:
            state.last_processed_message_id = result.last_message_id
        self.save_state(state)
        logger.info(
            "Poller processed %s email(s); cursor=%s",
            result.processed,
            state.last_processed_message_id,
        )
        return result.as_dict()

    def run_once(self) -> dict[str, Any]:
        """Run a single processing pass synchronously (for tests or manual invoke)."""
        state = self.get_state()
        payload = self._tick(state)
        return payload
