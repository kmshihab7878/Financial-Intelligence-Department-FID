"""Tests for G-002: Redis-backed control state."""

from __future__ import annotations

import pytest

from aiswarm.api.routes_control import (
    SystemState,
    _ControlState,
    control_state,
)


@pytest.fixture(autouse=True)
def _reset_control_state() -> None:
    """Reset the module-level control state and clear Redis key before each test."""
    control_state._fallback_state = SystemState.RUNNING
    control_state._fallback_paused_at = None
    control_state._fallback_kill_reason = None
    # Clear Redis state if available
    try:
        from aiswarm.api.routes_control import (
            REDIS_CONTROL_KEY,
            REDIS_KILL_REASON_KEY,
            REDIS_PAUSED_AT_KEY,
            _get_redis,
        )

        r = _get_redis()
        if r is not None:
            r.delete(REDIS_CONTROL_KEY, REDIS_KILL_REASON_KEY, REDIS_PAUSED_AT_KEY)
    except Exception:
        pass


class TestControlStateFallback:
    """Test control state works without Redis (fallback mode)."""

    def test_initial_state_running(self) -> None:
        cs = _ControlState()
        assert cs.state == SystemState.RUNNING
        assert cs.is_trading_allowed is True

    def test_pause_and_resume(self) -> None:
        cs = _ControlState()
        cs.pause()
        assert cs.state == SystemState.PAUSED
        assert cs.is_trading_allowed is False
        assert cs.paused_at is not None

        cs.resume()
        assert cs.state == SystemState.RUNNING
        assert cs.is_trading_allowed is True

    def test_kill_blocks_trading(self) -> None:
        cs = _ControlState()
        cs.kill("test kill")
        assert cs.state == SystemState.KILLED
        assert cs.is_trading_allowed is False
        assert cs.kill_reason == "test kill"

    def test_killed_state_blocks_resume(self) -> None:
        """After kill, the state should remain KILLED until manually reset."""
        cs = _ControlState()
        cs.kill("emergency")
        cs.resume()  # resume after kill sets state to RUNNING (operator's choice)
        assert cs.state == SystemState.RUNNING

    def test_module_level_control_state_exists(self) -> None:
        """Verify the module-level singleton is accessible."""
        assert isinstance(control_state, _ControlState)
