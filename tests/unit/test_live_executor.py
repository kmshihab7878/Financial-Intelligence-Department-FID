"""Tests for the live order executor."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

import pytest

from aiswarm.data.event_store import EventStore
from aiswarm.data.providers.aster_config import AsterConfig, Venue
from aiswarm.execution.aster_executor import AsterExecutor, ExecutionMode
from aiswarm.execution.live_executor import LiveOrderExecutor
from aiswarm.execution.mcp_gateway import MockMCPGateway
from aiswarm.execution.order_store import OrderStore
from aiswarm.risk.limits import sign_risk_token
from aiswarm.types.orders import Order, OrderStatus, Side


def _make_store() -> EventStore:
    return EventStore(tempfile.mktemp(suffix=".db"))


def _make_order(order_id: str = "o1") -> Order:
    return Order(
        order_id=order_id,
        signal_id="s1",
        symbol="BTCUSDT",
        side=Side.BUY,
        quantity=0.1,
        limit_price=None,
        notional=5000.0,
        strategy="momentum",
        thesis="valid test thesis",
        created_at=datetime.now(timezone.utc),
        risk_approval_token=sign_risk_token(order_id),
        status=OrderStatus.APPROVED,
    )


@pytest.fixture(autouse=True)
def _env() -> None:
    os.environ["AIS_RISK_HMAC_SECRET"] = "test-secret-for-ci"


class TestLiveOrderExecutor:
    def test_paper_mode_submit(self) -> None:
        executor = AsterExecutor(mode=ExecutionMode.PAPER)
        gateway = MockMCPGateway()
        store = OrderStore(_make_store())

        live = LiveOrderExecutor(executor, gateway, store)
        result = live.submit_order(_make_order())

        assert result.success
        assert result.exchange_order_id is not None
        assert "paper" in result.exchange_order_id
        assert len(gateway.call_history) == 0  # No MCP calls in paper mode

    def test_paper_mode_records_fill(self) -> None:
        executor = AsterExecutor(mode=ExecutionMode.PAPER)
        gateway = MockMCPGateway()
        store = OrderStore(_make_store())

        live = LiveOrderExecutor(executor, gateway, store)
        live.submit_order(_make_order())

        record = store.get("o1")
        assert record is not None
        assert record.order.status == OrderStatus.FILLED

    def test_live_mode_submit(self) -> None:
        os.environ["AIS_ENABLE_LIVE_TRADING"] = "true"
        os.environ["ASTER_ACCOUNT_ID"] = "test_account"
        try:
            config = AsterConfig(account_id="test_account")
            executor = AsterExecutor(config=config, mode=ExecutionMode.LIVE)
            gateway = MockMCPGateway()
            store = OrderStore(_make_store())

            live = LiveOrderExecutor(executor, gateway, store)
            result = live.submit_order(_make_order())

            assert result.success
            assert result.exchange_order_id is not None
            assert len(gateway.call_history) == 1
            assert gateway.call_history[0].tool_name == "mcp__aster__create_order"
        finally:
            os.environ.pop("AIS_ENABLE_LIVE_TRADING", None)
            os.environ.pop("ASTER_ACCOUNT_ID", None)

    def test_live_mode_submit_spot(self) -> None:
        os.environ["AIS_ENABLE_LIVE_TRADING"] = "true"
        os.environ["ASTER_ACCOUNT_ID"] = "test_account"
        try:
            config = AsterConfig(account_id="test_account")
            executor = AsterExecutor(config=config, mode=ExecutionMode.LIVE)
            gateway = MockMCPGateway()
            store = OrderStore(_make_store())

            live = LiveOrderExecutor(executor, gateway, store, default_venue=Venue.SPOT)
            result = live.submit_order(_make_order())

            assert result.success
            assert gateway.call_history[0].tool_name == "mcp__aster__create_spot_order"
        finally:
            os.environ.pop("AIS_ENABLE_LIVE_TRADING", None)
            os.environ.pop("ASTER_ACCOUNT_ID", None)

    def test_cancel_order(self) -> None:
        os.environ["AIS_ENABLE_LIVE_TRADING"] = "true"
        os.environ["ASTER_ACCOUNT_ID"] = "test_account"
        try:
            config = AsterConfig(account_id="test_account")
            executor = AsterExecutor(config=config, mode=ExecutionMode.LIVE)
            gateway = MockMCPGateway()
            store = OrderStore(_make_store())

            live = LiveOrderExecutor(executor, gateway, store)
            live.submit_order(_make_order())

            result = live.cancel_order("o1")
            assert result.success
            record = store.get("o1")
            assert record is not None
            assert record.order.status == OrderStatus.CANCELLED
        finally:
            os.environ.pop("AIS_ENABLE_LIVE_TRADING", None)
            os.environ.pop("ASTER_ACCOUNT_ID", None)

    def test_cancel_nonexistent_order(self) -> None:
        executor = AsterExecutor(mode=ExecutionMode.PAPER)
        gateway = MockMCPGateway()
        store = OrderStore(_make_store())

        live = LiveOrderExecutor(executor, gateway, store)
        result = live.cancel_order("nonexistent")
        assert not result.success

    def test_cancel_all(self) -> None:
        os.environ["AIS_ENABLE_LIVE_TRADING"] = "true"
        os.environ["ASTER_ACCOUNT_ID"] = "test_account"
        try:
            config = AsterConfig(account_id="test_account")
            executor = AsterExecutor(config=config, mode=ExecutionMode.LIVE)
            gateway = MockMCPGateway()
            store = OrderStore(_make_store())

            live = LiveOrderExecutor(executor, gateway, store)
            results = live.cancel_all(["BTCUSDT"])
            # 2 results: futures + spot for 1 symbol
            assert len(results) == 2
            assert all(r.success for r in results)
        finally:
            os.environ.pop("AIS_ENABLE_LIVE_TRADING", None)
            os.environ.pop("ASTER_ACCOUNT_ID", None)

    def test_submission_failure_records_cancel(self) -> None:
        os.environ["AIS_ENABLE_LIVE_TRADING"] = "true"
        os.environ["ASTER_ACCOUNT_ID"] = "test_account"
        try:
            config = AsterConfig(account_id="test_account")
            executor = AsterExecutor(config=config, mode=ExecutionMode.LIVE)
            gateway = MockMCPGateway()
            # Set response with no orderId to trigger failure
            gateway.set_response("mcp__aster__create_order", {})
            store = OrderStore(_make_store())

            live = LiveOrderExecutor(executor, gateway, store)
            result = live.submit_order(_make_order())
            assert not result.success
        finally:
            os.environ.pop("AIS_ENABLE_LIVE_TRADING", None)
            os.environ.pop("ASTER_ACCOUNT_ID", None)
