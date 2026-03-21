"""Shared fixtures for integration tests."""

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
from aiswarm.types.portfolio import PortfolioSnapshot


@pytest.fixture(autouse=True, scope="session")
def _set_hmac_secret() -> None:
    os.environ["AIS_RISK_HMAC_SECRET"] = "test-secret-for-integration"


@pytest.fixture()
def shared_memory() -> SharedMemory:
    memory = SharedMemory()
    snapshot = PortfolioSnapshot(
        timestamp=datetime.now(timezone.utc),
        nav=100_000.0,
        cash=100_000.0,
        gross_exposure=0.0,
        net_exposure=0.0,
        positions=[],
    )
    memory.update_snapshot(snapshot)
    return memory


@pytest.fixture()
def risk_engine() -> RiskEngine:
    return RiskEngine(
        max_position_weight=0.10,
        max_gross_exposure=1.5,
        max_daily_loss=0.03,
        max_rolling_drawdown=0.05,
        max_leverage=3.0,
        min_liquidity_score=0.3,
    )


@pytest.fixture()
def coordinator(shared_memory: SharedMemory, risk_engine: RiskEngine) -> Coordinator:
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        decision_log_path = f.name

    arbitration = WeightedArbitration(weights={"momentum_agent": 1.0, "funding_rate_agent": 0.8})
    allocator = PortfolioAllocator(target_weight=0.02)

    return Coordinator(
        arbitration=arbitration,
        allocator=allocator,
        risk_engine=risk_engine,
        memory=shared_memory,
        decision_log_path=decision_log_path,
    )
