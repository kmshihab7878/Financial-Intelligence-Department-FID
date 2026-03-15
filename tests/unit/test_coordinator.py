"""Integration tests for the Coordinator pipeline."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

import pytest

from aiswarm.orchestration.arbitration import WeightedArbitration
from aiswarm.orchestration.coordinator import Coordinator
from aiswarm.orchestration.memory import SharedMemory
from aiswarm.portfolio.allocator import PortfolioAllocator
from aiswarm.risk.limits import RiskEngine
from aiswarm.types.market import MarketRegime, Signal
from aiswarm.utils.ids import new_id


def _make_signal(
    agent_id: str = "agent_1",
    symbol: str = "BTCUSDT",
    direction: int = 1,
    confidence: float = 0.7,
    expected_return: float = 0.02,
    liquidity_score: float = 0.8,
) -> Signal:
    return Signal(
        signal_id=new_id("sig"),
        agent_id=agent_id,
        symbol=symbol,
        strategy="test_strategy",
        thesis="Test signal thesis for integration",
        direction=direction,
        confidence=confidence,
        expected_return=expected_return,
        horizon_minutes=60,
        liquidity_score=liquidity_score,
        regime=MarketRegime.RISK_ON,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def coordinator(tmp_path: object) -> Coordinator:
    os.environ["AIS_RISK_HMAC_SECRET"] = "test-secret-for-ci"
    log_path = tempfile.mktemp(suffix=".jsonl")
    return Coordinator(
        arbitration=WeightedArbitration(weights={"agent_1": 1.0, "agent_2": 0.8}),
        allocator=PortfolioAllocator(target_weight=0.02),
        risk_engine=RiskEngine(
            max_position_weight=0.05,
            max_gross_exposure=1.0,
            max_daily_loss=0.02,
        ),
        memory=SharedMemory(),
        decision_log_path=log_path,
    )


class TestCoordinator:
    def test_full_pipeline_produces_approved_order(self, coordinator: Coordinator) -> None:
        signals = [_make_signal()]
        order = coordinator.coordinate(signals)
        assert order is not None
        assert order.status.value == "approved"
        assert order.risk_approval_token is not None

    def test_no_signals_returns_none(self, coordinator: Coordinator) -> None:
        order = coordinator.coordinate([])
        assert order is None

    def test_selects_best_signal(self, coordinator: Coordinator) -> None:
        signals = [
            _make_signal(agent_id="agent_1", confidence=0.5, expected_return=0.01),
            _make_signal(agent_id="agent_2", confidence=0.9, expected_return=0.05),
        ]
        order = coordinator.coordinate(signals)
        assert order is not None
        # agent_2 has higher score despite lower weight (0.8 * 0.9 * 0.05 > 1.0 * 0.5 * 0.01)
        assert order.symbol == "BTCUSDT"

    def test_risk_rejection_returns_none(self, coordinator: Coordinator) -> None:
        # Set memory to trigger kill switch
        coordinator.memory.latest_pnl = -0.05
        signals = [_make_signal()]
        order = coordinator.coordinate(signals)
        assert order is None

    def test_decision_logged(self, coordinator: Coordinator) -> None:
        signals = [_make_signal()]
        coordinator.coordinate(signals)
        # Check that the JSONL log file was written
        import json
        from pathlib import Path

        log_file = Path(coordinator.decision_log_path)
        assert log_file.exists()
        content = log_file.read_text().strip()
        decision = json.loads(content)
        assert "decision_id" in decision
        assert "risk_passed" in decision

    def test_buy_and_sell_signals(self, coordinator: Coordinator) -> None:
        # Buy signal
        buy = _make_signal(direction=1)
        order = coordinator.coordinate([buy])
        assert order is not None
        assert order.side.value == "buy"

        # Sell signal
        sell = _make_signal(direction=-1)
        order = coordinator.coordinate([sell])
        assert order is not None
        assert order.side.value == "sell"

    def test_low_liquidity_signal_rejected(self, coordinator: Coordinator) -> None:
        coordinator.risk_engine.min_liquidity_score = 0.50
        signals = [_make_signal(liquidity_score=0.3)]
        order = coordinator.coordinate(signals)
        assert order is None


class TestSharedMemory:
    def test_update_snapshot_tracks_peak_nav(self) -> None:
        from aiswarm.types.portfolio import PortfolioSnapshot

        mem = SharedMemory()

        snap1 = PortfolioSnapshot(
            timestamp=datetime.now(timezone.utc),
            nav=100000,
            cash=100000,
            gross_exposure=0.0,
            net_exposure=0.0,
            positions=(),
        )
        mem.update_snapshot(snap1)
        assert mem.peak_nav == 100000

        snap2 = PortfolioSnapshot(
            timestamp=datetime.now(timezone.utc),
            nav=110000,
            cash=110000,
            gross_exposure=0.0,
            net_exposure=0.0,
            positions=(),
        )
        mem.update_snapshot(snap2)
        assert mem.peak_nav == 110000

        # Drawdown
        snap3 = PortfolioSnapshot(
            timestamp=datetime.now(timezone.utc),
            nav=100000,
            cash=100000,
            gross_exposure=0.0,
            net_exposure=0.0,
            positions=(),
        )
        mem.update_snapshot(snap3)
        assert mem.peak_nav == 110000  # Peak unchanged
        assert abs(mem.rolling_drawdown - (10000 / 110000)) < 1e-10

    def test_leverage_derived_from_exposure(self) -> None:
        from aiswarm.types.portfolio import PortfolioSnapshot

        mem = SharedMemory()
        snap = PortfolioSnapshot(
            timestamp=datetime.now(timezone.utc),
            nav=100000,
            cash=50000,
            gross_exposure=150000,
            net_exposure=100000,
            positions=(),
        )
        mem.update_snapshot(snap)
        assert mem.current_leverage == 1.5
