"""Tests for daily review report generation."""

from __future__ import annotations

from datetime import datetime, timezone

import tempfile

from aiswarm.data.event_store import EventStore
from aiswarm.mandates.models import MandateRiskBudget
from aiswarm.mandates.registry import MandateRegistry
from aiswarm.orchestration.memory import SharedMemory
from aiswarm.review.generator import ReviewGenerator
from aiswarm.session.models import SessionState, TradingSession


def _make_store() -> EventStore:
    return EventStore(tempfile.mktemp(suffix=".db"))


def _make_session() -> TradingSession:
    now = datetime.now(timezone.utc)
    return TradingSession(
        session_id="sess_1",
        state=SessionState.ENDED,
        scheduled_start=now,
        scheduled_end=now,
        actual_start=now,
        actual_end=now,
        created_at=now,
    )


class TestReviewGenerator:
    def test_generates_report(self) -> None:
        store = _make_store()
        registry = MandateRegistry(store)
        memory = SharedMemory()

        budget = MandateRiskBudget(
            max_capital=10000.0,
            max_daily_loss=0.02,
            max_drawdown=0.05,
        )
        registry.create("m1", "momentum", ("BTCUSDT",), budget)

        generator = ReviewGenerator(store, registry, memory)
        session = _make_session()

        report = generator.generate_daily_report(session)
        assert report.report_id.startswith("review_")
        assert report.session_id == "sess_1"
        assert report.total_fills == 0
        assert report.reconciliation_passed
        assert len(report.mandate_summaries) >= 1

    def test_report_aggregates_fills(self) -> None:
        from datetime import timedelta

        store = _make_store()
        registry = MandateRegistry(store)
        memory = SharedMemory()

        budget = MandateRiskBudget(
            max_capital=10000.0,
            max_daily_loss=0.02,
            max_drawdown=0.05,
        )
        registry.create("m1", "momentum", ("BTCUSDT",), budget)

        # Add some fill events
        store.append(
            "fill",
            {"mandate_id": "m1", "pnl": 50.0, "symbol": "BTCUSDT"},
            source="test",
        )
        store.append(
            "fill",
            {"mandate_id": "m1", "pnl": -20.0, "symbol": "BTCUSDT"},
            source="test",
        )

        # Session start must be BEFORE the fills were recorded
        now = datetime.now(timezone.utc)
        session = TradingSession(
            session_id="sess_1",
            state=SessionState.ENDED,
            scheduled_start=now - timedelta(minutes=5),
            scheduled_end=now + timedelta(minutes=5),
            actual_start=now - timedelta(minutes=5),
            actual_end=now + timedelta(minutes=5),
            created_at=now - timedelta(minutes=5),
        )

        generator = ReviewGenerator(store, registry, memory)
        report = generator.generate_daily_report(session)
        assert report.total_fills == 2
        assert abs(report.total_pnl - 30.0) < 1e-6

    def test_report_persisted_to_event_store(self) -> None:
        store = _make_store()
        registry = MandateRegistry(store)
        memory = SharedMemory()

        generator = ReviewGenerator(store, registry, memory)
        session = _make_session()
        generator.generate_daily_report(session)

        events = store.get_events(event_type="daily_review", limit=10)
        assert len(events) >= 1
