"""Tests for the persistent order store."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone

from aiswarm.data.event_store import EventStore
from aiswarm.execution.order_store import OrderStore
from aiswarm.types.orders import Order, OrderStatus, Side


def _make_store() -> EventStore:
    return EventStore(tempfile.mktemp(suffix=".db"))


def _make_order(order_id: str = "o1", symbol: str = "BTCUSDT") -> Order:
    return Order(
        order_id=order_id,
        signal_id="s1",
        symbol=symbol,
        side=Side.BUY,
        quantity=0.1,
        limit_price=None,
        notional=5000.0,
        strategy="momentum",
        thesis="valid test thesis",
        created_at=datetime.now(timezone.utc),
        risk_approval_token="fake_token",
        status=OrderStatus.APPROVED,
    )


class TestOrderStore:
    def test_track_and_get(self) -> None:
        store = OrderStore(_make_store())
        order = _make_order()
        record = store.track(order)
        assert record.order.order_id == "o1"
        assert store.get("o1") is not None

    def test_record_submission(self) -> None:
        store = OrderStore(_make_store())
        store.track(_make_order())
        record = store.record_submission("o1", "EX00000001")
        assert record is not None
        assert record.exchange_order_id == "EX00000001"
        assert record.order.status == OrderStatus.SUBMITTED

    def test_get_by_exchange_id(self) -> None:
        store = OrderStore(_make_store())
        store.track(_make_order())
        store.record_submission("o1", "EX00000001")
        record = store.get_by_exchange_id("EX00000001")
        assert record is not None
        assert record.order.order_id == "o1"

    def test_record_fill(self) -> None:
        store = OrderStore(_make_store())
        store.track(_make_order())
        store.record_submission("o1", "EX00000001")
        record = store.record_fill("o1", fill_price=50000.0, fill_quantity=0.1)
        assert record is not None
        assert record.fill_price == 50000.0
        assert record.order.status == OrderStatus.FILLED

    def test_record_cancel(self) -> None:
        store = OrderStore(_make_store())
        store.track(_make_order())
        store.record_submission("o1", "EX00000001")
        record = store.record_cancel("o1", "timeout")
        assert record is not None
        assert record.order.status == OrderStatus.CANCELLED

    def test_get_open_orders(self) -> None:
        store = OrderStore(_make_store())
        store.track(_make_order("o1"))
        store.track(_make_order("o2"))
        store.record_submission("o1", "EX1")
        store.record_submission("o2", "EX2")
        store.record_fill("o1", 50000.0, 0.1)

        open_orders = store.get_open_orders()
        assert len(open_orders) == 1
        assert open_orders[0].order.order_id == "o2"

    def test_known_exchange_ids(self) -> None:
        store = OrderStore(_make_store())
        store.track(_make_order("o1"))
        store.track(_make_order("o2"))
        store.record_submission("o1", "EX1")
        store.record_submission("o2", "EX2")

        assert store.known_exchange_ids == {"EX1", "EX2"}

    def test_get_nonexistent_returns_none(self) -> None:
        store = OrderStore(_make_store())
        assert store.get("nonexistent") is None
        assert store.get_by_exchange_id("nonexistent") is None

    def test_events_persisted(self) -> None:
        es = _make_store()
        store = OrderStore(es)
        store.track(_make_order())
        store.record_submission("o1", "EX1")
        store.record_fill("o1", 50000.0, 0.1)

        tracked = es.get_events(event_type="order_tracked", limit=10)
        submitted = es.get_events(event_type="order_submitted", limit=10)
        fills = es.get_events(event_type="fill", limit=10)

        assert len(tracked) >= 1
        assert len(submitted) >= 1
        assert len(fills) >= 1
