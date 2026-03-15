"""Tests for the Order Management System."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from aiswarm.execution.oms import OMS
from aiswarm.risk.limits import sign_risk_token
from aiswarm.types.orders import Order, OrderStatus, Side


def _make_order(
    order_id: str = "o1",
    risk_token: str | None = None,
) -> Order:
    return Order(
        order_id=order_id,
        signal_id="s1",
        symbol="BTCUSDT",
        side=Side.BUY,
        quantity=1.0,
        limit_price=None,
        notional=1000.0,
        strategy="test",
        thesis="valid test thesis",
        risk_approval_token=risk_token,
        created_at=datetime.now(timezone.utc),
    )


class TestOMS:
    def setup_method(self) -> None:
        os.environ["AIS_RISK_HMAC_SECRET"] = "test-secret-for-ci"

    def test_submit_with_valid_token(self) -> None:
        oms = OMS()
        token = sign_risk_token("o1")
        order = _make_order(risk_token=token)
        result = oms.submit(order)
        assert result.status == OrderStatus.SUBMITTED

    def test_submit_without_token_raises(self) -> None:
        oms = OMS()
        order = _make_order()
        with pytest.raises(ValueError, match="risk approval token required"):
            oms.submit(order)

    def test_submit_with_invalid_token_raises(self) -> None:
        oms = OMS()
        order = _make_order(risk_token="fake:token:value")
        with pytest.raises(ValueError, match="invalid or expired"):
            oms.submit(order)

    def test_submit_with_wrong_order_id_token_raises(self) -> None:
        oms = OMS()
        # Sign for different order ID
        token = sign_risk_token("other_order")
        order = _make_order(risk_token=token)
        with pytest.raises(ValueError, match="invalid or expired"):
            oms.submit(order)
