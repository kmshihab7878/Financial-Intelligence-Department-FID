"""Tests for G-015: stale order cancellation."""

from __future__ import annotations

import tempfile

import pytest

from aiswarm.data.event_store import EventStore
from aiswarm.execution.order_store import OrderStore
from aiswarm.types.orders import Order, Side
from aiswarm.utils.ids import new_id
from aiswarm.utils.time import utc_now


@pytest.fixture
def order_store() -> OrderStore:
    es = EventStore(tempfile.mktemp(suffix=".db"))
    return OrderStore(es)


def _make_order() -> Order:
    return Order(
        order_id=new_id("ord"),
        signal_id=new_id("sig"),
        symbol="BTCUSDT",
        side=Side.BUY,
        quantity=0.1,
        notional=1000.0,
        strategy="test",
        thesis="Test order for timeout",
        created_at=utc_now(),
    )


class TestOrderTimeout:
    def test_submitted_at_set_on_submission(self, order_store: OrderStore) -> None:
        order = _make_order()
        order_store.track(order)
        record = order_store.record_submission(order.order_id, "EX001")
        assert record is not None
        assert record.submitted_at > 0

    def test_get_stale_orders_empty_when_fresh(self, order_store: OrderStore) -> None:
        order = _make_order()
        order_store.track(order)
        order_store.record_submission(order.order_id, "EX001")
        stale = order_store.get_stale_orders(max_age_seconds=300.0)
        assert len(stale) == 0

    def test_get_stale_orders_returns_old_orders(self, order_store: OrderStore) -> None:
        order = _make_order()
        order_store.track(order)
        order_store.record_submission(order.order_id, "EX001")
        # Use a very short max_age so the order is immediately stale.
        # This avoids issues with time.monotonic() on fresh CI containers.
        stale = order_store.get_stale_orders(max_age_seconds=0.0)
        assert len(stale) == 1
        assert stale[0].order.order_id == order.order_id

    def test_filled_orders_not_returned_as_stale(self, order_store: OrderStore) -> None:
        order = _make_order()
        order_store.track(order)
        order_store.record_submission(order.order_id, "EX001")
        order_store.record_fill(order.order_id, 50000.0, 0.1)
        # Even with max_age=0 (everything is stale), filled orders are excluded
        stale = order_store.get_stale_orders(max_age_seconds=0.0)
        assert len(stale) == 0
