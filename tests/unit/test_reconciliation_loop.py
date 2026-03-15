"""Tests for ReconciliationLoop auto-pause on mismatch."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone

from aiswarm.data.event_store import EventStore
from aiswarm.data.providers.aster import ExchangePosition
from aiswarm.monitoring.reconciliation import (
    PositionReconciler,
    ReconciliationLoop,
)
from aiswarm.types.portfolio import PortfolioSnapshot, Position


def _make_store() -> EventStore:
    return EventStore(tempfile.mktemp(suffix=".db"))


def _make_position(
    symbol: str = "BTCUSDT",
    quantity: float = 1.0,
    price: float = 50000.0,
) -> Position:
    return Position(
        symbol=symbol,
        quantity=quantity,
        avg_price=price,
        market_price=price,
        strategy="test",
    )


def _make_snapshot(positions: tuple[Position, ...] = ()) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        timestamp=datetime.now(timezone.utc),
        nav=100_000,
        cash=100_000,
        gross_exposure=0.0,
        net_exposure=0.0,
        positions=positions,
    )


class TestReconciliationLoop:
    def test_on_fill_matching_no_pause(self) -> None:
        store = _make_store()
        paused: list[bool] = []
        loop = ReconciliationLoop(
            reconciler=PositionReconciler(provider=None, tolerance=0.001),
            event_store=store,
            pause_callback=lambda: paused.append(True),
        )

        snapshot = _make_snapshot()
        report = loop.on_fill(snapshot, [])
        assert report.passed
        assert len(paused) == 0

    def test_on_fill_mismatch_triggers_pause(self) -> None:
        store = _make_store()
        paused: list[bool] = []
        loop = ReconciliationLoop(
            reconciler=PositionReconciler(provider=None, tolerance=0.001),
            event_store=store,
            pause_callback=lambda: paused.append(True),
        )

        snapshot = _make_snapshot(positions=(_make_position(quantity=1.0),))

        # Exchange has different quantity
        exchange_positions = [
            ExchangePosition(
                symbol="BTCUSDT",
                side="LONG",
                quantity=2.0,  # Mismatch!
                entry_price=50000,
                mark_price=50000,
                unrealized_pnl=0.0,
                leverage=1,
                margin_mode="CROSSED",
            )
        ]

        report = loop.on_fill(snapshot, exchange_positions)
        assert not report.passed
        assert len(paused) == 1

    def test_periodic_check_persists_report(self) -> None:
        store = _make_store()
        loop = ReconciliationLoop(
            reconciler=PositionReconciler(provider=None, tolerance=0.001),
            event_store=store,
            pause_callback=lambda: None,
        )

        snapshot = _make_snapshot()
        loop.run_periodic_check(snapshot, [])

        events = store.get_events(event_type="reconciliation", limit=10)
        assert len(events) >= 1

    def test_mismatch_threshold(self) -> None:
        """Pause only triggered when mismatches exceed threshold."""
        store = _make_store()
        paused: list[bool] = []
        loop = ReconciliationLoop(
            reconciler=PositionReconciler(provider=None, tolerance=0.001),
            event_store=store,
            pause_callback=lambda: paused.append(True),
            mismatch_threshold=1,  # Allow 1 mismatch before pausing
        )

        snapshot = _make_snapshot(positions=(_make_position(quantity=1.0),))

        exchange_positions = [
            ExchangePosition(
                symbol="BTCUSDT",
                side="LONG",
                quantity=2.0,
                entry_price=50000,
                mark_price=50000,
                unrealized_pnl=0.0,
                leverage=1,
                margin_mode="CROSSED",
            )
        ]

        # 1 mismatch <= threshold of 1, so no pause
        report = loop.on_fill(snapshot, exchange_positions)
        assert not report.passed
        assert len(paused) == 0

    def test_latest_report_stored(self) -> None:
        store = _make_store()
        loop = ReconciliationLoop(
            reconciler=PositionReconciler(provider=None, tolerance=0.001),
            event_store=store,
            pause_callback=lambda: None,
        )

        assert loop.latest_report is None
        loop.on_fill(_make_snapshot(), [])
        assert loop.latest_report is not None

    def test_pause_event_persisted(self) -> None:
        store = _make_store()
        loop = ReconciliationLoop(
            reconciler=PositionReconciler(provider=None, tolerance=0.001),
            event_store=store,
            pause_callback=lambda: None,
            mismatch_threshold=0,
        )

        snapshot = _make_snapshot(positions=(_make_position(quantity=1.0),))
        exchange_positions = [
            ExchangePosition(
                symbol="BTCUSDT",
                side="LONG",
                quantity=5.0,
                entry_price=50000,
                mark_price=50000,
                unrealized_pnl=0.0,
                leverage=1,
                margin_mode="CROSSED",
            )
        ]

        loop.on_fill(snapshot, exchange_positions)

        pause_events = store.get_events(event_type="reconciliation_pause", limit=10)
        assert len(pause_events) >= 1
