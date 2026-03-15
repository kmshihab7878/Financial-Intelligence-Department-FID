"""Graceful shutdown handler.

Catches SIGINT/SIGTERM, saves state checkpoint via EventStore,
and allows in-flight work to complete before exit.

Usage::

    event_store = EventStore()
    memory = SharedMemory()

    handler = GracefulShutdown(event_store=event_store, memory=memory)
    handler.install()

    while handler.is_running:
        # main loop
        ...

    # After loop exits, handler has already saved checkpoint
"""

from __future__ import annotations

import signal
import threading
from typing import Any, Callable

from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)


class GracefulShutdown:
    """Manages graceful shutdown with state checkpointing.

    On receiving SIGINT or SIGTERM:
    1. Sets ``is_running`` to False (main loop should check this)
    2. Calls all registered shutdown callbacks in order
    3. Saves a checkpoint via the provided ``checkpoint_fn``
    """

    def __init__(
        self,
        checkpoint_fn: Callable[[], None] | None = None,
    ) -> None:
        self._running = True
        self._shutdown_initiated = False
        self._lock = threading.Lock()
        self._callbacks: list[Callable[[], None]] = []
        self._checkpoint_fn = checkpoint_fn

    @property
    def is_running(self) -> bool:
        return self._running

    def install(self) -> None:
        """Install signal handlers for SIGINT and SIGTERM."""
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        logger.info("Graceful shutdown handler installed")

    def register_callback(self, fn: Callable[[], None]) -> None:
        """Register a callback to run during shutdown (LIFO order)."""
        with self._lock:
            self._callbacks.append(fn)

    def initiate_shutdown(self, reason: str = "manual") -> None:
        """Programmatically initiate shutdown."""
        with self._lock:
            if self._shutdown_initiated:
                return
            self._shutdown_initiated = True
            self._running = False

        logger.warning(
            "Shutdown initiated",
            extra={"extra_json": {"reason": reason}},
        )
        self._run_callbacks()
        self._save_checkpoint()

    def _handle_signal(self, signum: int, frame: Any) -> None:
        """Signal handler for SIGINT/SIGTERM."""
        sig_name = signal.Signals(signum).name
        self.initiate_shutdown(reason=f"signal:{sig_name}")

    def _run_callbacks(self) -> None:
        """Run registered callbacks in reverse order (LIFO)."""
        for callback in reversed(self._callbacks):
            try:
                callback()
            except Exception as exc:
                logger.error(
                    "Shutdown callback failed",
                    extra={"extra_json": {"error": str(exc)}},
                )

    def _save_checkpoint(self) -> None:
        """Save state checkpoint if a checkpoint function was provided."""
        if self._checkpoint_fn is None:
            return
        try:
            self._checkpoint_fn()
            logger.info("Shutdown checkpoint saved")
        except Exception as exc:
            logger.error(
                "Failed to save shutdown checkpoint",
                extra={"extra_json": {"error": str(exc)}},
            )
