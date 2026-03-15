"""Tests for graceful shutdown handler."""

from __future__ import annotations

from aiswarm.resilience.shutdown import GracefulShutdown


class TestGracefulShutdown:
    def test_starts_running(self) -> None:
        handler = GracefulShutdown()
        assert handler.is_running

    def test_initiate_shutdown(self) -> None:
        handler = GracefulShutdown()
        handler.initiate_shutdown(reason="test")
        assert not handler.is_running

    def test_calls_checkpoint_fn(self) -> None:
        called = []
        handler = GracefulShutdown(checkpoint_fn=lambda: called.append(True))
        handler.initiate_shutdown(reason="test")
        assert called == [True]

    def test_calls_registered_callbacks_in_lifo_order(self) -> None:
        order: list[int] = []
        handler = GracefulShutdown()
        handler.register_callback(lambda: order.append(1))
        handler.register_callback(lambda: order.append(2))
        handler.register_callback(lambda: order.append(3))
        handler.initiate_shutdown(reason="test")
        assert order == [3, 2, 1]

    def test_double_shutdown_is_idempotent(self) -> None:
        call_count = []
        handler = GracefulShutdown(checkpoint_fn=lambda: call_count.append(1))
        handler.initiate_shutdown(reason="first")
        handler.initiate_shutdown(reason="second")
        assert len(call_count) == 1

    def test_callback_error_does_not_prevent_checkpoint(self) -> None:
        checkpoint_called = []

        def failing_callback() -> None:
            raise RuntimeError("callback failed")

        handler = GracefulShutdown(checkpoint_fn=lambda: checkpoint_called.append(True))
        handler.register_callback(failing_callback)
        handler.initiate_shutdown(reason="test")
        assert checkpoint_called == [True]

    def test_no_checkpoint_fn_is_ok(self) -> None:
        handler = GracefulShutdown(checkpoint_fn=None)
        handler.initiate_shutdown(reason="test")
        assert not handler.is_running
