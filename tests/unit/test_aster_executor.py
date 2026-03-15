"""Tests for the Aster DEX execution adapter."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from aiswarm.data.providers.aster_config import AsterConfig, Venue
from aiswarm.execution.aster_executor import AsterExecutor, ExecutionMode
from aiswarm.risk.limits import sign_risk_token
from aiswarm.types.orders import Order, Side


def _make_order(
    order_id: str = "o1",
    symbol: str = "BTCUSDT",
    side: Side = Side.BUY,
    risk_token: str | None = None,
) -> Order:
    return Order(
        order_id=order_id,
        signal_id="s1",
        symbol=symbol,
        side=side,
        quantity=0.1,
        limit_price=50000.0,
        notional=5000.0,
        strategy="test",
        thesis="valid test thesis",
        risk_approval_token=risk_token,
        created_at=datetime.now(timezone.utc),
    )


class TestAsterExecutor:
    def setup_method(self) -> None:
        os.environ["AIS_RISK_HMAC_SECRET"] = "test-secret-for-ci"
        os.environ.pop("AIS_ENABLE_LIVE_TRADING", None)

    def test_paper_mode_default(self) -> None:
        config = AsterConfig(account_id="test_acc")
        executor = AsterExecutor(config=config, mode=ExecutionMode.PAPER)
        assert executor.mode == ExecutionMode.PAPER

    def test_live_mode_requires_env_flag(self) -> None:
        config = AsterConfig(account_id="test_acc")
        with pytest.raises(RuntimeError, match="AIS_ENABLE_LIVE_TRADING"):
            AsterExecutor(config=config, mode=ExecutionMode.LIVE)

    def test_live_mode_requires_account_id(self) -> None:
        os.environ["AIS_ENABLE_LIVE_TRADING"] = "true"
        config = AsterConfig(account_id="")
        with pytest.raises(RuntimeError, match="ASTER_ACCOUNT_ID"):
            AsterExecutor(config=config, mode=ExecutionMode.LIVE)

    def test_prepare_futures_order(self) -> None:
        config = AsterConfig(account_id="acc123")
        executor = AsterExecutor(config=config, mode=ExecutionMode.PAPER)
        token = sign_risk_token("o1")
        order = _make_order(risk_token=token)
        params = executor.prepare_futures_order(order)
        assert params["account_id"] == "acc123"
        assert params["symbol"] == "BTCUSDT"
        assert params["side"] == "BUY"
        assert params["order_type"] == "LIMIT"
        assert params["quantity"] == 0.1
        assert params["price"] == 50000.0

    def test_prepare_spot_order(self) -> None:
        config = AsterConfig(account_id="acc123")
        executor = AsterExecutor(config=config, mode=ExecutionMode.PAPER)
        token = sign_risk_token("o1")
        order = _make_order(risk_token=token)
        params = executor.prepare_spot_order(order)
        assert params["account_id"] == "acc123"
        assert params["order_type"] == "LIMIT"

    def test_prepare_order_without_token_raises(self) -> None:
        config = AsterConfig(account_id="acc123")
        executor = AsterExecutor(config=config, mode=ExecutionMode.PAPER)
        order = _make_order()
        with pytest.raises(ValueError, match="risk approval token"):
            executor.prepare_futures_order(order)

    def test_simulate_paper_fill(self) -> None:
        config = AsterConfig(account_id="acc123")
        executor = AsterExecutor(config=config, mode=ExecutionMode.PAPER)
        token = sign_risk_token("o1")
        order = _make_order(risk_token=token)
        result = executor.simulate_paper_fill(order, current_price=50100.0)
        assert result.success
        assert result.fill_price == 50000.0  # Uses limit price
        assert result.fill_quantity == 0.1
        assert executor.paper_fill_count == 1

    def test_paper_fill_uses_market_price_when_no_limit(self) -> None:
        config = AsterConfig(account_id="acc123")
        executor = AsterExecutor(config=config, mode=ExecutionMode.PAPER)
        order = Order(
            order_id="o2",
            signal_id="s1",
            symbol="BTCUSDT",
            side=Side.BUY,
            quantity=0.1,
            limit_price=None,
            notional=5000.0,
            strategy="test",
            thesis="valid test thesis",
            risk_approval_token=sign_risk_token("o2"),
            created_at=datetime.now(timezone.utc),
        )
        result = executor.simulate_paper_fill(order, current_price=50100.0)
        assert result.fill_price == 50100.0

    def test_prepare_cancel_all(self) -> None:
        config = AsterConfig(account_id="acc123")
        executor = AsterExecutor(config=config, mode=ExecutionMode.PAPER)
        params = executor.prepare_cancel_all("BTCUSDT", Venue.FUTURES)
        assert params["tool"] == "mcp__aster__cancel_all_orders"
        assert params["symbol"] == "BTCUSDT"

    def test_prepare_emergency_cancel_all(self) -> None:
        config = AsterConfig(account_id="acc123")
        executor = AsterExecutor(config=config, mode=ExecutionMode.PAPER)
        cancels = executor.prepare_emergency_cancel_all(["BTCUSDT", "ETHUSDT"])
        assert len(cancels) == 4  # 2 symbols × 2 venues

    def test_prepare_set_leverage(self) -> None:
        config = AsterConfig(account_id="acc123")
        executor = AsterExecutor(config=config, mode=ExecutionMode.PAPER)
        params = executor.prepare_set_leverage("BTCUSDT", 5)
        assert params["leverage"] == 5

    def test_prepare_set_margin_mode(self) -> None:
        config = AsterConfig(account_id="acc123")
        executor = AsterExecutor(config=config, mode=ExecutionMode.PAPER)
        params = executor.prepare_set_margin_mode("BTCUSDT", "ISOLATED")
        assert params["margin_mode"] == "ISOLATED"
