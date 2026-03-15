"""Tests for session manager lifecycle."""

from __future__ import annotations

from datetime import time

import pytest

import tempfile

from aiswarm.data.event_store import EventStore
from aiswarm.session.manager import SessionManager
from aiswarm.session.models import SessionState


def _make_store() -> EventStore:
    return EventStore(tempfile.mktemp(suffix=".db"))


class TestSessionManager:
    def test_create_and_start_session(self) -> None:
        store = _make_store()
        mgr = SessionManager(store)

        session = mgr.start_session()
        assert session is not None
        assert session.state == SessionState.PENDING_REVIEW
        assert not mgr.is_trading_allowed

    def test_approve_session(self) -> None:
        store = _make_store()
        mgr = SessionManager(store)

        mgr.start_session()
        mgr.approve_session("operator_1", "looks good")
        assert mgr.current_session is not None
        assert mgr.current_session.state == SessionState.APPROVED

    def test_activate_session(self) -> None:
        store = _make_store()
        mgr = SessionManager(store)

        mgr.start_session()
        mgr.approve_session("operator_1")
        mgr.activate_session()
        assert mgr.is_trading_allowed
        assert mgr.current_session is not None
        assert mgr.current_session.state == SessionState.ACTIVE

    def test_end_session(self) -> None:
        store = _make_store()
        mgr = SessionManager(store)

        mgr.start_session()
        mgr.approve_session("operator_1")
        mgr.activate_session()
        assert mgr.is_trading_allowed

        mgr.end_session()
        assert not mgr.is_trading_allowed
        assert mgr.current_session is not None
        assert mgr.current_session.state == SessionState.ENDED

    def test_full_lifecycle(self) -> None:
        store = _make_store()
        mgr = SessionManager(store)

        # Start
        mgr.start_session()
        assert not mgr.is_trading_allowed

        # Approve
        mgr.approve_session("ops_lead", "daily review complete")
        assert not mgr.is_trading_allowed  # Not yet active

        # Activate
        mgr.activate_session()
        assert mgr.is_trading_allowed

        # End
        mgr.end_session()
        assert not mgr.is_trading_allowed

    def test_cannot_approve_without_session(self) -> None:
        store = _make_store()
        mgr = SessionManager(store)

        with pytest.raises(ValueError, match="No current session"):
            mgr.approve_session("operator")

    def test_cannot_approve_active_session(self) -> None:
        store = _make_store()
        mgr = SessionManager(store)

        mgr.start_session()
        mgr.approve_session("operator_1")
        mgr.activate_session()

        with pytest.raises(ValueError, match="not in.*prerequisite"):
            mgr.approve_session("operator_2")

    def test_cannot_activate_unapproved_session(self) -> None:
        store = _make_store()
        mgr = SessionManager(store)

        mgr.start_session()
        with pytest.raises(ValueError, match="not in.*prerequisite"):
            mgr.activate_session()

    def test_session_schedule(self) -> None:
        store = _make_store()
        schedule = {
            "start_time": time(9, 0),
            "end_time": time(17, 0),
        }
        mgr = SessionManager(store, schedule=schedule)
        session = mgr.start_session()
        # Should record the schedule in session
        assert session is not None

    def test_session_persists_events(self) -> None:
        store = _make_store()
        mgr = SessionManager(store)

        mgr.start_session()
        mgr.approve_session("operator_1")
        mgr.activate_session()
        mgr.end_session()

        # Check events were persisted
        events = store.get_events(event_type="session", limit=100)
        assert len(events) >= 4  # start, approve, activate, end

    def test_no_session_means_trading_not_allowed(self) -> None:
        store = _make_store()
        mgr = SessionManager(store)
        assert not mgr.is_trading_allowed
