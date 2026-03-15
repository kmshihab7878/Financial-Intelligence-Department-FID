"""Tests for the fill tracker service."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone

from aiswarm.data.event_store import EventStore
from aiswarm.execution.fill_tracker import FillTracker
from aiswarm.execution.mcp_gateway import MockMCPGateway
from aiswarm.execution.order_store import OrderStore
from aiswarm.orchestration.memory import SharedMemory
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
        mandate_id="m1",
    )


class TestFillTracker:
    def test_no_trades_returns_zero(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response("mcp__aster__get_my_trades", {"trades": []})
        store = OrderStore(_make_store())
        memory = SharedMemory()

        tracker = FillTracker(gateway, store, memory)
        result = tracker.sync_fills("BTCUSDT")
        assert result.matched_fills == 0
        assert result.total_exchange_trades == 0

    def test_matches_fill_to_order(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__aster__get_my_trades",
            [
                {
                    "id": "T001",
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "price": "50000.0",
                    "qty": "0.1",
                    "commission": "5.0",
                    "realizedPnl": "25.0",
                    "time": 1700000000000,
                },
            ],
        )

        es = _make_store()
        store = OrderStore(es)
        order = _make_order()
        store.track(order)
        store.record_submission("o1", "EX001")

        memory = SharedMemory()
        tracker = FillTracker(gateway, store, memory)
        result = tracker.sync_fills("BTCUSDT")

        assert result.matched_fills == 1
        record = store.get("o1")
        assert record is not None
        assert record.fill_price == 50000.0

    def test_updates_mandate_pnl(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__aster__get_my_trades",
            [
                {
                    "id": "T001",
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "price": "50000.0",
                    "qty": "0.1",
                    "commission": "5.0",
                    "realizedPnl": "100.0",
                    "time": 1700000000000,
                },
            ],
        )

        store = OrderStore(_make_store())
        order = _make_order()
        store.track(order)
        store.record_submission("o1", "EX001")

        memory = SharedMemory()
        tracker = FillTracker(gateway, store, memory)
        tracker.sync_fills("BTCUSDT")

        mandate_tracker = memory.get_mandate_tracker("m1")
        assert mandate_tracker.daily_pnl == 100.0

    def test_unmatched_trades(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__aster__get_my_trades",
            [
                {
                    "id": "T999",
                    "symbol": "ETHUSDT",
                    "side": "SELL",
                    "price": "3000.0",
                    "qty": "1.0",
                    "commission": "3.0",
                    "realizedPnl": "0",
                    "time": 1700000000000,
                },
            ],
        )

        store = OrderStore(_make_store())
        memory = SharedMemory()
        tracker = FillTracker(gateway, store, memory)
        result = tracker.sync_fills("ETHUSDT")

        assert result.unmatched_fills == 1
        assert result.matched_fills == 0

    def test_check_order_status(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__aster__get_order",
            {"orderId": "EX001", "status": "FILLED", "symbol": "BTCUSDT"},
        )

        store = OrderStore(_make_store())
        store.track(_make_order())
        store.record_submission("o1", "EX001")

        memory = SharedMemory()
        tracker = FillTracker(gateway, store, memory)
        status = tracker.check_order_status("o1", "BTCUSDT")
        assert status == "FILLED"

    def test_check_order_status_unknown(self) -> None:
        gateway = MockMCPGateway()
        store = OrderStore(_make_store())
        memory = SharedMemory()
        tracker = FillTracker(gateway, store, memory)
        status = tracker.check_order_status("nonexistent", "BTCUSDT")
        assert status is None
