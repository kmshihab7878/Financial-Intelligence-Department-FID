"""Tests for mandate-aware risk validation."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from aiswarm.mandates.models import Mandate, MandateRiskBudget
from aiswarm.orchestration.memory import MandatePnLTracker, SharedMemory
from aiswarm.risk.limits import RiskEngine
from aiswarm.types.orders import Order, Side


def _make_order(
    order_id: str = "o1",
    notional: float = 1000.0,
) -> Order:
    return Order(
        order_id=order_id,
        signal_id="s1",
        symbol="BTCUSDT",
        side=Side.BUY,
        quantity=1.0,
        limit_price=None,
        notional=notional,
        strategy="momentum",
        thesis="valid test thesis",
        created_at=datetime.now(timezone.utc),
    )


def _make_mandate(
    max_capital: float = 10000.0,
    max_daily_loss: float = 0.02,
    max_drawdown: float = 0.05,
    max_position_notional: float = 0.0,
) -> Mandate:
    return Mandate(
        mandate_id="m1",
        strategy="momentum",
        symbols=("BTCUSDT",),
        risk_budget=MandateRiskBudget(
            max_capital=max_capital,
            max_daily_loss=max_daily_loss,
            max_drawdown=max_drawdown,
            max_position_notional=max_position_notional,
        ),
        created_at=datetime.now(timezone.utc),
    )


class TestMandateRiskValidation:
    def setup_method(self) -> None:
        os.environ["AIS_RISK_HMAC_SECRET"] = "test-secret-for-ci"

    def test_passes_when_within_mandate_limits(self) -> None:
        engine = RiskEngine(0.05, 1.0, 0.02)
        order = _make_order(notional=1000.0)
        mandate = _make_mandate(max_capital=10000.0)
        tracker = MandatePnLTracker(mandate_id="m1")

        approval = engine.validate_with_mandate(
            order=order,
            snapshot=None,
            daily_pnl_fraction=0.0,
            rolling_drawdown=0.0,
            current_leverage=0.0,
            liquidity_score=0.8,
            mandate=mandate,
            mandate_tracker=tracker,
        )
        assert approval.approved

    def test_rejects_on_mandate_daily_loss(self) -> None:
        engine = RiskEngine(0.05, 1.0, 0.02)
        order = _make_order()
        mandate = _make_mandate(max_capital=10000.0, max_daily_loss=0.02)
        tracker = MandatePnLTracker(mandate_id="m1", daily_pnl=-300.0)  # 3% loss

        approval = engine.validate_with_mandate(
            order=order,
            snapshot=None,
            daily_pnl_fraction=0.0,
            rolling_drawdown=0.0,
            current_leverage=0.0,
            liquidity_score=0.8,
            mandate=mandate,
            mandate_tracker=tracker,
        )
        assert not approval.approved
        assert any("mandate_daily_loss" in r for r in approval.reasons)

    def test_rejects_on_mandate_drawdown(self) -> None:
        engine = RiskEngine(0.05, 1.0, 0.02)
        order = _make_order()
        mandate = _make_mandate(max_drawdown=0.05)
        tracker = MandatePnLTracker(
            mandate_id="m1",
            peak_nav=10000.0,
            current_nav=9000.0,  # 10% drawdown > 5% limit
        )

        approval = engine.validate_with_mandate(
            order=order,
            snapshot=None,
            daily_pnl_fraction=0.0,
            rolling_drawdown=0.0,
            current_leverage=0.0,
            liquidity_score=0.8,
            mandate=mandate,
            mandate_tracker=tracker,
        )
        assert not approval.approved
        assert any("mandate_drawdown" in r for r in approval.reasons)

    def test_rejects_on_mandate_capital_exceeded(self) -> None:
        engine = RiskEngine(0.05, 1.0, 0.02)
        order = _make_order(notional=6000.0)
        mandate = _make_mandate(max_capital=10000.0)
        tracker = MandatePnLTracker(mandate_id="m1", gross_exposure=6000.0)

        approval = engine.validate_with_mandate(
            order=order,
            snapshot=None,
            daily_pnl_fraction=0.0,
            rolling_drawdown=0.0,
            current_leverage=0.0,
            liquidity_score=0.8,
            mandate=mandate,
            mandate_tracker=tracker,
        )
        assert not approval.approved
        assert any("mandate_capital" in r for r in approval.reasons)

    def test_rejects_on_position_notional_exceeded(self) -> None:
        engine = RiskEngine(0.05, 1.0, 0.02)
        order = _make_order(notional=2000.0)
        mandate = _make_mandate(max_position_notional=1500.0)
        tracker = MandatePnLTracker(mandate_id="m1")

        approval = engine.validate_with_mandate(
            order=order,
            snapshot=None,
            daily_pnl_fraction=0.0,
            rolling_drawdown=0.0,
            current_leverage=0.0,
            liquidity_score=0.8,
            mandate=mandate,
            mandate_tracker=tracker,
        )
        assert not approval.approved
        assert any("mandate_position_notional" in r for r in approval.reasons)

    def test_global_rejection_takes_precedence(self) -> None:
        engine = RiskEngine(0.05, 1.0, 0.02)
        order = _make_order()
        mandate = _make_mandate()
        tracker = MandatePnLTracker(mandate_id="m1")

        # Trigger global kill switch with daily loss
        approval = engine.validate_with_mandate(
            order=order,
            snapshot=None,
            daily_pnl_fraction=-0.05,
            rolling_drawdown=0.0,
            current_leverage=0.0,
            liquidity_score=0.8,
            mandate=mandate,
            mandate_tracker=tracker,
        )
        assert not approval.approved
        assert any("kill_switch" in r for r in approval.reasons)

    def test_stricter_of_two_wins(self) -> None:
        """If global passes but mandate fails, order is rejected."""
        engine = RiskEngine(0.05, 1.0, 0.10)  # Generous global daily loss
        order = _make_order()
        mandate = _make_mandate(max_daily_loss=0.01, max_capital=10000.0)
        tracker = MandatePnLTracker(mandate_id="m1", daily_pnl=-150.0)  # 1.5% > 1%

        approval = engine.validate_with_mandate(
            order=order,
            snapshot=None,
            daily_pnl_fraction=0.0,
            rolling_drawdown=0.0,
            current_leverage=0.0,
            liquidity_score=0.8,
            mandate=mandate,
            mandate_tracker=tracker,
        )
        assert not approval.approved


class TestMandatePnLTracker:
    def test_drawdown_calculation(self) -> None:
        tracker = MandatePnLTracker(
            mandate_id="m1",
            peak_nav=10000.0,
            current_nav=9500.0,
        )
        assert abs(tracker.drawdown - 0.05) < 1e-10

    def test_drawdown_zero_when_no_peak(self) -> None:
        tracker = MandatePnLTracker(mandate_id="m1")
        assert tracker.drawdown == 0.0

    def test_shared_memory_mandate_tracking(self) -> None:
        mem = SharedMemory()

        # Get or create tracker
        tracker = mem.get_mandate_tracker("m1")
        assert tracker.mandate_id == "m1"
        assert tracker.daily_pnl == 0.0

        # Update P&L
        mem.update_mandate_pnl("m1", 100.0)
        assert mem.mandate_trackers["m1"].daily_pnl == 100.0
        assert mem.mandate_trackers["m1"].current_nav == 100.0
        assert mem.mandate_trackers["m1"].peak_nav == 100.0

        # Negative P&L
        mem.update_mandate_pnl("m1", -150.0)
        assert mem.mandate_trackers["m1"].daily_pnl == -50.0
        assert mem.mandate_trackers["m1"].current_nav == -50.0
        assert mem.mandate_trackers["m1"].peak_nav == 100.0  # Peak unchanged

    def test_reset_daily_mandate_pnl(self) -> None:
        mem = SharedMemory()
        mem.update_mandate_pnl("m1", -100.0)
        mem.update_mandate_pnl("m2", 200.0)

        mem.reset_daily_mandate_pnl()
        assert mem.mandate_trackers["m1"].daily_pnl == 0.0
        assert mem.mandate_trackers["m2"].daily_pnl == 0.0
        # Current NAV should not be reset
        assert mem.mandate_trackers["m1"].current_nav == -100.0
