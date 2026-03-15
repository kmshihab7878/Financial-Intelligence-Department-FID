"""Tests for G-004: mandate strategy names must match agent strategies."""

from __future__ import annotations

import tempfile

import pytest

from aiswarm.agents.market_intelligence.funding_rate_agent import FundingRateAgent
from aiswarm.agents.strategy.momentum_agent import MomentumAgent
from aiswarm.bootstrap import validate_mandate_strategies
from aiswarm.data.event_store import EventStore
from aiswarm.mandates.models import MandateRiskBudget
from aiswarm.mandates.registry import MandateRegistry


@pytest.fixture
def event_store(tmp_path: object) -> EventStore:
    return EventStore(tempfile.mktemp(suffix=".db"))


@pytest.fixture
def budget() -> MandateRiskBudget:
    return MandateRiskBudget(
        max_capital=10000.0,
        max_daily_loss=0.02,
        max_drawdown=0.05,
    )


class TestMandateStrategyValidation:
    def test_valid_strategies_pass(
        self, event_store: EventStore, budget: MandateRiskBudget
    ) -> None:
        registry = MandateRegistry(event_store)
        registry.create(
            "m1", strategy="momentum_ma_crossover", symbols=("BTCUSDT",), risk_budget=budget
        )
        registry.create(
            "m2", strategy="funding_rate_contrarian", symbols=("ETHUSDT",), risk_budget=budget
        )

        agents = [MomentumAgent(), FundingRateAgent()]
        # Should not raise
        validate_mandate_strategies(registry, agents)

    def test_invalid_strategy_raises(
        self, event_store: EventStore, budget: MandateRiskBudget
    ) -> None:
        registry = MandateRegistry(event_store)
        registry.create(
            "m1", strategy="nonexistent_strategy", symbols=("BTCUSDT",), risk_budget=budget
        )

        agents = [MomentumAgent(), FundingRateAgent()]
        with pytest.raises(RuntimeError, match="nonexistent_strategy"):
            validate_mandate_strategies(registry, agents)

    def test_old_momentum_strategy_name_fails(
        self, event_store: EventStore, budget: MandateRiskBudget
    ) -> None:
        """The old 'momentum' strategy name (pre-fix) should be rejected."""
        registry = MandateRegistry(event_store)
        registry.create("m1", strategy="momentum", symbols=("BTCUSDT",), risk_budget=budget)

        agents = [MomentumAgent(), FundingRateAgent()]
        with pytest.raises(RuntimeError, match="momentum"):
            validate_mandate_strategies(registry, agents)
