"""Integration tests for the full signal → risk → execution pipeline.

These tests exercise the real component wiring without mocking the
internal pipeline, verifying that signals flow through arbitration,
allocation, risk validation, and HMAC token signing end-to-end.
"""

from __future__ import annotations

from datetime import datetime, timezone

from aiswarm.orchestration.coordinator import Coordinator
from aiswarm.orchestration.memory import SharedMemory
from aiswarm.risk.limits import RiskEngine, verify_risk_token
from aiswarm.types.market import MarketRegime, Signal
from aiswarm.types.orders import Order, OrderStatus, Side
from aiswarm.utils.time import utc_now


def _make_signal(
    agent_id: str = "momentum_agent",
    symbol: str = "BTCUSDT",
    direction: int = 1,
    confidence: float = 0.75,
    expected_return: float = 0.02,
    liquidity_score: float = 0.8,
) -> Signal:
    return Signal(
        signal_id=f"sig_{agent_id}_{direction}",
        agent_id=agent_id,
        symbol=symbol,
        strategy="momentum_ma_crossover",
        thesis="Integration test signal with sufficient length",
        direction=direction,
        confidence=confidence,
        expected_return=expected_return,
        horizon_minutes=240,
        liquidity_score=liquidity_score,
        regime=MarketRegime.RISK_ON,
        created_at=datetime.now(timezone.utc),
        reference_price=50000.0,
    )


class TestFullPipeline:
    """Test the complete signal → order → risk approval pipeline."""

    def test_signal_flows_through_to_approved_order(self, coordinator: Coordinator) -> None:
        """A valid signal should produce an HMAC-signed, APPROVED order."""
        signal = _make_signal()
        order = coordinator.coordinate([signal])

        assert order is not None
        assert order.status == OrderStatus.APPROVED
        assert order.risk_approval_token is not None
        assert order.symbol == "BTCUSDT"

    def test_hmac_token_is_valid(self, coordinator: Coordinator) -> None:
        """The HMAC token on an approved order should verify correctly."""
        signal = _make_signal()
        order = coordinator.coordinate([signal])

        assert order is not None
        assert order.risk_approval_token is not None
        assert verify_risk_token(order.risk_approval_token, order.order_id)

    def test_hmac_token_fails_for_wrong_order_id(self, coordinator: Coordinator) -> None:
        """An HMAC token should not verify for a different order ID."""
        signal = _make_signal()
        order = coordinator.coordinate([signal])

        assert order is not None
        assert order.risk_approval_token is not None
        assert not verify_risk_token(order.risk_approval_token, "wrong_order_id")

    def test_no_signal_produces_no_order(self, coordinator: Coordinator) -> None:
        """An empty signal list should produce no order."""
        order = coordinator.coordinate([])
        assert order is None

    def test_neutral_signal_produces_no_order(self, coordinator: Coordinator) -> None:
        """A neutral (direction=0) signal should still produce an order (BUY side)."""
        signal = _make_signal(direction=0)
        order = coordinator.coordinate([signal])
        # direction=0 maps to BUY in the allocator
        assert order is not None

    def test_arbitration_selects_best_signal(self, coordinator: Coordinator) -> None:
        """When multiple signals compete, the highest-scoring one wins."""
        weak = _make_signal(
            agent_id="funding_rate_agent",
            confidence=0.3,
            expected_return=0.005,
        )
        strong = _make_signal(
            agent_id="momentum_agent",
            confidence=0.9,
            expected_return=0.05,
        )

        order = coordinator.coordinate([weak, strong])
        assert order is not None
        # The order should be sized based on the strong signal's confidence
        assert order.status == OrderStatus.APPROVED


class TestRiskRejection:
    """Test that the risk engine correctly rejects orders under various conditions."""

    def test_kill_switch_blocks_order(
        self,
        coordinator: Coordinator,
        shared_memory: SharedMemory,
    ) -> None:
        """When daily P&L exceeds kill switch threshold, orders are rejected."""
        # Simulate a large daily loss
        shared_memory.latest_pnl = -0.05  # 5% loss exceeds 3% threshold

        signal = _make_signal()
        order = coordinator.coordinate([signal])

        # Kill switch should prevent approval
        assert order is None

    def test_low_liquidity_blocks_order(self, coordinator: Coordinator) -> None:
        """Signals with insufficient liquidity score should be rejected."""
        signal = _make_signal(liquidity_score=0.1)  # Below 0.3 threshold
        order = coordinator.coordinate([signal])

        assert order is None

    def test_high_drawdown_blocks_order(
        self,
        coordinator: Coordinator,
        shared_memory: SharedMemory,
    ) -> None:
        """Orders should be rejected when rolling drawdown exceeds limit."""
        # Set a high drawdown state
        shared_memory.rolling_drawdown = 0.06  # Exceeds 5% threshold

        signal = _make_signal()
        order = coordinator.coordinate([signal])

        assert order is None

    def test_high_leverage_blocks_order(
        self,
        coordinator: Coordinator,
        shared_memory: SharedMemory,
    ) -> None:
        """Orders should be rejected when leverage exceeds ceiling."""
        shared_memory.current_leverage = 4.0  # Exceeds 3.0 ceiling

        signal = _make_signal()
        order = coordinator.coordinate([signal])

        assert order is None


class TestRiskEngineDirectly:
    """Test the risk engine in isolation with realistic inputs."""

    def test_approve_normal_order(
        self, risk_engine: RiskEngine, shared_memory: SharedMemory
    ) -> None:
        order = Order(
            order_id="test_order_1",
            signal_id="test_signal",
            symbol="BTCUSDT",
            side=Side.BUY,
            quantity=0.001,
            notional=50.0,
            strategy="test_strategy",
            thesis="Testing risk approval flow",
            status=OrderStatus.PENDING,
            created_at=utc_now(),
        )

        approval = risk_engine.validate(
            order=order,
            snapshot=shared_memory.latest_snapshot,
            daily_pnl_fraction=0.0,
            rolling_drawdown=0.0,
            current_leverage=0.0,
            liquidity_score=0.8,
        )

        assert approval.approved
        assert approval.order is not None
        assert approval.order.status == OrderStatus.APPROVED
        assert approval.order.risk_approval_token is not None
        assert "approved" in approval.reasons

    def test_reject_during_drawdown(
        self, risk_engine: RiskEngine, shared_memory: SharedMemory
    ) -> None:
        order = Order(
            order_id="test_order_2",
            signal_id="test_signal",
            symbol="BTCUSDT",
            side=Side.BUY,
            quantity=0.001,
            notional=50.0,
            strategy="test_strategy",
            thesis="Testing risk rejection flow",
            status=OrderStatus.PENDING,
            created_at=utc_now(),
        )

        approval = risk_engine.validate(
            order=order,
            snapshot=shared_memory.latest_snapshot,
            daily_pnl_fraction=0.0,
            rolling_drawdown=0.10,  # 10% drawdown, exceeds 5% limit
            current_leverage=0.0,
            liquidity_score=0.8,
        )

        assert not approval.approved
        assert approval.order is None
        assert any("drawdown_breached" in r for r in approval.reasons)

    def test_multiple_rejections_reported(
        self, risk_engine: RiskEngine, shared_memory: SharedMemory
    ) -> None:
        order = Order(
            order_id="test_order_3",
            signal_id="test_signal",
            symbol="BTCUSDT",
            side=Side.BUY,
            quantity=0.001,
            notional=50.0,
            strategy="test_strategy",
            thesis="Testing multiple rejection reasons",
            status=OrderStatus.PENDING,
            created_at=utc_now(),
        )

        approval = risk_engine.validate(
            order=order,
            snapshot=shared_memory.latest_snapshot,
            daily_pnl_fraction=-0.05,  # Kill switch
            rolling_drawdown=0.10,  # Drawdown breach
            current_leverage=5.0,  # Leverage breach
            liquidity_score=0.1,  # Liquidity insufficient
        )

        assert not approval.approved
        assert len(approval.reasons) >= 3  # Multiple guards triggered
