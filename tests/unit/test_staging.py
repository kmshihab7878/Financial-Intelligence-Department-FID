"""Tests for staging workflow and coordinator integration with mandates/sessions."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

import pytest

from aiswarm.data.event_store import EventStore
from aiswarm.mandates.models import MandateRiskBudget
from aiswarm.mandates.registry import MandateRegistry
from aiswarm.mandates.validator import MandateValidator
from aiswarm.orchestration.arbitration import WeightedArbitration
from aiswarm.orchestration.coordinator import Coordinator
from aiswarm.orchestration.memory import SharedMemory
from aiswarm.portfolio.allocator import PortfolioAllocator
from aiswarm.risk.limits import RiskEngine
from aiswarm.session.manager import SessionManager
from aiswarm.types.market import MarketRegime, Signal
from aiswarm.utils.ids import new_id


def _make_store() -> EventStore:
    return EventStore(tempfile.mktemp(suffix=".db"))


def _make_signal(
    strategy: str = "momentum",
    symbol: str = "BTCUSDT",
) -> Signal:
    return Signal(
        signal_id=new_id("sig"),
        agent_id="agent_1",
        symbol=symbol,
        strategy=strategy,
        thesis="Test signal thesis for staging",
        direction=1,
        confidence=0.7,
        expected_return=0.02,
        horizon_minutes=60,
        liquidity_score=0.8,
        regime=MarketRegime.RISK_ON,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture(autouse=True)
def _set_hmac_secret() -> None:
    os.environ["AIS_RISK_HMAC_SECRET"] = "test-secret-for-ci"


def _build_coordinator(
    staging_enabled: bool = False,
    with_mandates: bool = False,
    with_session: bool = False,
) -> Coordinator:
    store = _make_store()
    log_path = tempfile.mktemp(suffix=".jsonl")

    mandate_validator = None
    if with_mandates:
        registry = MandateRegistry(store)
        registry.create(
            "m_momentum",
            "momentum",
            ("BTCUSDT", "ETHUSDT"),
            MandateRiskBudget(
                max_capital=50000.0,
                max_daily_loss=0.02,
                max_drawdown=0.05,
            ),
        )
        mandate_validator = MandateValidator(registry)

    session_manager = None
    if with_session:
        session_manager = SessionManager(store)

    return Coordinator(
        arbitration=WeightedArbitration(weights={"agent_1": 1.0}),
        allocator=PortfolioAllocator(target_weight=0.02),
        risk_engine=RiskEngine(
            max_position_weight=0.05,
            max_gross_exposure=1.0,
            max_daily_loss=0.02,
        ),
        memory=SharedMemory(),
        decision_log_path=log_path,
        mandate_validator=mandate_validator,
        session_manager=session_manager,
        staging_enabled=staging_enabled,
    )


class TestBackwardCompatibility:
    """Phase 2 behavior is preserved when no mandates/sessions configured."""

    def test_no_mandates_no_session_same_as_phase2(self) -> None:
        coord = _build_coordinator()
        order = coord.coordinate([_make_signal()])
        assert order is not None
        assert order.status.value == "approved"

    def test_no_signals_still_returns_none(self) -> None:
        coord = _build_coordinator()
        assert coord.coordinate([]) is None


class TestMandateIntegration:
    def test_matching_mandate_approves(self) -> None:
        coord = _build_coordinator(with_mandates=True)
        order = coord.coordinate([_make_signal(strategy="momentum", symbol="BTCUSDT")])
        assert order is not None
        assert order.mandate_id == "m_momentum"

    def test_no_matching_mandate_rejects(self) -> None:
        coord = _build_coordinator(with_mandates=True)
        order = coord.coordinate([_make_signal(strategy="unknown_strat", symbol="BTCUSDT")])
        assert order is None


class TestSessionGating:
    def test_session_gate_blocks_when_not_active(self) -> None:
        coord = _build_coordinator(with_session=True)
        # Session exists but is PENDING_REVIEW — should block
        coord.session_manager.start_session()  # type: ignore[union-attr]
        order = coord.coordinate([_make_signal()])
        assert order is None

    def test_session_gate_allows_when_active(self) -> None:
        coord = _build_coordinator(with_session=True)
        mgr = coord.session_manager
        assert mgr is not None
        mgr.start_session()
        mgr.approve_session("test_operator")
        mgr.activate_session()

        order = coord.coordinate([_make_signal()])
        assert order is not None

    def test_session_gate_blocks_after_end(self) -> None:
        coord = _build_coordinator(with_session=True)
        mgr = coord.session_manager
        assert mgr is not None
        mgr.start_session()
        mgr.approve_session("test_operator")
        mgr.activate_session()
        mgr.end_session()

        order = coord.coordinate([_make_signal()])
        assert order is None


class TestStagingWorkflow:
    def test_staging_holds_order(self) -> None:
        coord = _build_coordinator(staging_enabled=True)
        order = coord.coordinate([_make_signal()])
        # With staging enabled, coordinate returns None
        assert order is None
        # But the order is staged
        staged = coord.get_staged_orders()
        assert len(staged) == 1
        assert staged[0].status.value == "staged"

    def test_execute_staged_order(self) -> None:
        coord = _build_coordinator(staging_enabled=True)
        coord.coordinate([_make_signal()])

        staged = coord.get_staged_orders()
        assert len(staged) == 1

        executed = coord.execute_staged(staged[0].order_id)
        assert executed is not None
        assert executed.status.value == "approved"

        # Now staging dict is empty
        assert len(coord.get_staged_orders()) == 0

    def test_reject_staged_order(self) -> None:
        coord = _build_coordinator(staging_enabled=True)
        coord.coordinate([_make_signal()])

        staged = coord.get_staged_orders()
        assert len(staged) == 1

        rejected = coord.reject_staged(staged[0].order_id, "not today")
        assert rejected is not None
        assert rejected.status.value == "rejected"

        assert len(coord.get_staged_orders()) == 0

    def test_execute_nonexistent_order(self) -> None:
        coord = _build_coordinator(staging_enabled=True)
        assert coord.execute_staged("nonexistent") is None

    def test_staging_with_mandates(self) -> None:
        coord = _build_coordinator(staging_enabled=True, with_mandates=True)
        coord.coordinate([_make_signal(strategy="momentum", symbol="BTCUSDT")])

        staged = coord.get_staged_orders()
        assert len(staged) == 1
        assert staged[0].mandate_id == "m_momentum"
