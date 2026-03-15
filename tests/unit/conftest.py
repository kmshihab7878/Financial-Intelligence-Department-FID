"""Shared fixtures and factory functions for AIS unit tests.

Consolidates duplicated test helpers that were previously copy-pasted across
multiple test modules: _make_order, _make_snapshot, _make_position, _make_store,
and the AIS_RISK_HMAC_SECRET environment variable setup.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

import pytest

from aiswarm.data.event_store import EventStore
from aiswarm.types.orders import Order, OrderStatus, Side
from aiswarm.types.portfolio import PortfolioSnapshot, Position


# ---------------------------------------------------------------------------
# Session-scoped autouse fixture: ensure AIS_RISK_HMAC_SECRET is always set
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True, scope="session")
def _set_hmac_secret() -> None:
    """Set AIS_RISK_HMAC_SECRET for the entire test session.

    Many modules (risk engine, OMS, executors) read this env var at import or
    call time.  Setting it once at session scope avoids the need for every test
    class to repeat ``os.environ["AIS_RISK_HMAC_SECRET"] = ...`` in its own
    setup_method / fixture.
    """
    os.environ["AIS_RISK_HMAC_SECRET"] = "test-secret-for-ci"


# ---------------------------------------------------------------------------
# Factory helpers exposed as pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def make_order():
    """Factory fixture for creating Order instances with sensible defaults.

    Returns a callable so tests can customise individual fields:

        def test_something(make_order):
            order = make_order(symbol="ETHUSDT", notional=2000.0)
    """

    def _factory(
        order_id: str = "o1",
        signal_id: str = "s1",
        symbol: str = "BTCUSDT",
        side: Side = Side.BUY,
        quantity: float = 1.0,
        limit_price: float | None = None,
        notional: float = 1000.0,
        strategy: str = "test",
        thesis: str = "valid test thesis",
        mandate_id: str | None = None,
        risk_approval_token: str | None = None,
        status: OrderStatus = OrderStatus.PENDING,
        created_at: datetime | None = None,
    ) -> Order:
        return Order(
            order_id=order_id,
            signal_id=signal_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            limit_price=limit_price,
            notional=notional,
            strategy=strategy,
            thesis=thesis,
            mandate_id=mandate_id,
            risk_approval_token=risk_approval_token,
            status=status,
            created_at=created_at or datetime.now(timezone.utc),
        )

    return _factory


@pytest.fixture()
def make_snapshot():
    """Factory fixture for creating PortfolioSnapshot instances.

    Returns a callable:

        def test_something(make_snapshot):
            snap = make_snapshot(nav=50_000.0, gross_exposure=10_000.0)
    """

    def _factory(
        nav: float = 100_000.0,
        cash: float | None = None,
        gross_exposure: float = 0.0,
        net_exposure: float = 0.0,
        positions: tuple[Position, ...] = (),
        timestamp: datetime | None = None,
    ) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            timestamp=timestamp or datetime.now(timezone.utc),
            nav=nav,
            cash=cash if cash is not None else nav,
            gross_exposure=gross_exposure,
            net_exposure=net_exposure,
            positions=positions,
        )

    return _factory


@pytest.fixture()
def make_position():
    """Factory fixture for creating Position instances.

    Returns a callable:

        def test_something(make_position):
            pos = make_position(symbol="ETHUSDT", quantity=2.0)
    """

    def _factory(
        symbol: str = "BTCUSDT",
        quantity: float = 1.0,
        avg_price: float = 50_000.0,
        market_price: float = 50_000.0,
        strategy: str = "test",
    ) -> Position:
        return Position(
            symbol=symbol,
            quantity=quantity,
            avg_price=avg_price,
            market_price=market_price,
            strategy=strategy,
        )

    return _factory


@pytest.fixture()
def make_event_store():
    """Factory fixture that returns a fresh, temp-backed EventStore each call.

    Returns a callable:

        def test_something(make_event_store):
            store = make_event_store()
    """

    def _factory() -> EventStore:
        return EventStore(tempfile.mktemp(suffix=".db"))

    return _factory


@pytest.fixture()
def event_store() -> EventStore:
    """Convenience fixture providing a single EventStore instance per test."""
    return EventStore(tempfile.mktemp(suffix=".db"))
