"""Tests for mandate models, registry, and validator."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

import tempfile

from aiswarm.data.event_store import EventStore
from aiswarm.mandates.models import Mandate, MandateRiskBudget, MandateStatus
from aiswarm.mandates.registry import MandateRegistry
from aiswarm.mandates.validator import MandateValidator
from aiswarm.types.orders import Order, Side


def _make_store() -> EventStore:
    return EventStore(tempfile.mktemp(suffix=".db"))


def _make_order(
    symbol: str = "BTCUSDT",
    strategy: str = "momentum",
    notional: float = 1000.0,
) -> Order:
    return Order(
        order_id="o1",
        signal_id="s1",
        symbol=symbol,
        side=Side.BUY,
        quantity=1.0,
        limit_price=None,
        notional=notional,
        strategy=strategy,
        thesis="valid test thesis",
        created_at=datetime.now(timezone.utc),
    )


def _make_budget(
    max_capital: float = 10000.0,
    max_daily_loss: float = 0.02,
    max_drawdown: float = 0.05,
) -> MandateRiskBudget:
    return MandateRiskBudget(
        max_capital=max_capital,
        max_daily_loss=max_daily_loss,
        max_drawdown=max_drawdown,
    )


# --- Model Tests ---


class TestMandateModels:
    def test_mandate_creation(self) -> None:
        budget = _make_budget()
        mandate = Mandate(
            mandate_id="m1",
            strategy="momentum",
            symbols=("BTCUSDT",),
            risk_budget=budget,
            created_at=datetime.now(timezone.utc),
        )
        assert mandate.mandate_id == "m1"
        assert mandate.status == MandateStatus.ACTIVE
        assert mandate.symbols == ("BTCUSDT",)

    def test_mandate_status_values(self) -> None:
        assert MandateStatus.ACTIVE == "active"
        assert MandateStatus.PAUSED == "paused"
        assert MandateStatus.REVOKED == "revoked"

    def test_budget_effective_position_notional(self) -> None:
        budget = MandateRiskBudget(
            max_capital=10000.0,
            max_daily_loss=0.02,
            max_drawdown=0.05,
            max_position_notional=500.0,
        )
        assert budget.effective_position_notional == 500.0

    def test_budget_default_position_notional(self) -> None:
        budget = _make_budget(max_capital=10000.0)
        # Defaults to max_capital when max_position_notional is None
        assert budget.effective_position_notional == 10000.0

    def test_mandate_is_frozen(self) -> None:
        budget = _make_budget()
        mandate = Mandate(
            mandate_id="m1",
            strategy="momentum",
            symbols=("BTCUSDT",),
            risk_budget=budget,
            created_at=datetime.now(timezone.utc),
        )
        with pytest.raises(Exception):
            mandate.mandate_id = "m2"  # type: ignore[misc]


# --- Registry Tests ---


class TestMandateRegistry:
    def test_create_and_get(self, tmp_path: object) -> None:
        store = _make_store()
        registry = MandateRegistry(store)

        mandate = registry.create(
            mandate_id="m1",
            strategy="momentum",
            symbols=("BTCUSDT", "ETHUSDT"),
            risk_budget=_make_budget(),
        )
        assert mandate.mandate_id == "m1"

        retrieved = registry.get("m1")
        assert retrieved is not None
        assert retrieved.strategy == "momentum"

    def test_list_active(self) -> None:
        store = _make_store()
        registry = MandateRegistry(store)

        registry.create("m1", "momentum", ("BTCUSDT",), _make_budget())
        registry.create("m2", "mean_reversion", ("ETHUSDT",), _make_budget())
        registry.revoke("m2")

        active = registry.list_active()
        assert len(active) == 1
        assert active[0].mandate_id == "m1"

    def test_list_all(self) -> None:
        store = _make_store()
        registry = MandateRegistry(store)

        registry.create("m1", "momentum", ("BTCUSDT",), _make_budget())
        registry.create("m2", "mean_reversion", ("ETHUSDT",), _make_budget())
        registry.revoke("m2")

        all_mandates = registry.list_all()
        assert len(all_mandates) == 2

    def test_update_status(self) -> None:
        store = _make_store()
        registry = MandateRegistry(store)

        registry.create("m1", "momentum", ("BTCUSDT",), _make_budget())
        registry.update_status("m1", MandateStatus.PAUSED)

        mandate = registry.get("m1")
        assert mandate is not None
        assert mandate.status == MandateStatus.PAUSED

    def test_revoke(self) -> None:
        store = _make_store()
        registry = MandateRegistry(store)

        registry.create("m1", "momentum", ("BTCUSDT",), _make_budget())
        registry.revoke("m1")

        mandate = registry.get("m1")
        assert mandate is not None
        assert mandate.status == MandateStatus.REVOKED

    def test_find_mandate_for_order(self) -> None:
        store = _make_store()
        registry = MandateRegistry(store)

        registry.create("m1", "momentum", ("BTCUSDT", "ETHUSDT"), _make_budget())
        registry.create("m2", "mean_reversion", ("ETHUSDT",), _make_budget())

        # Match by strategy + symbol
        mandate = registry.find_mandate_for_order("momentum", "BTCUSDT")
        assert mandate is not None
        assert mandate.mandate_id == "m1"

        # Match ETHUSDT with mean_reversion
        mandate = registry.find_mandate_for_order("mean_reversion", "ETHUSDT")
        assert mandate is not None
        assert mandate.mandate_id == "m2"

        # No match
        mandate = registry.find_mandate_for_order("unknown_strat", "BTCUSDT")
        assert mandate is None

    def test_find_mandate_skips_inactive(self) -> None:
        store = _make_store()
        registry = MandateRegistry(store)

        registry.create("m1", "momentum", ("BTCUSDT",), _make_budget())
        registry.revoke("m1")

        mandate = registry.find_mandate_for_order("momentum", "BTCUSDT")
        assert mandate is None

    def test_get_nonexistent_returns_none(self) -> None:
        store = _make_store()
        registry = MandateRegistry(store)
        assert registry.get("nonexistent") is None


# --- Validator Tests ---


class TestMandateValidator:
    def test_validate_order_matches(self) -> None:
        store = _make_store()
        registry = MandateRegistry(store)
        registry.create("m1", "momentum", ("BTCUSDT",), _make_budget())

        validator = MandateValidator(registry)
        result = validator.validate_order(_make_order(strategy="momentum", symbol="BTCUSDT"))
        assert result.ok
        assert result.mandate is not None
        assert result.mandate.mandate_id == "m1"

    def test_validate_order_no_match(self) -> None:
        store = _make_store()
        registry = MandateRegistry(store)
        registry.create("m1", "momentum", ("BTCUSDT",), _make_budget())

        validator = MandateValidator(registry)
        result = validator.validate_order(_make_order(strategy="unknown", symbol="BTCUSDT"))
        assert not result.ok
        assert "No active mandate" in result.reason

    def test_validate_order_symbol_mismatch(self) -> None:
        store = _make_store()
        registry = MandateRegistry(store)
        registry.create("m1", "momentum", ("BTCUSDT",), _make_budget())

        validator = MandateValidator(registry)
        result = validator.validate_order(_make_order(strategy="momentum", symbol="XRPUSDT"))
        assert not result.ok

    def test_check_mandate_capital(self) -> None:
        validator = MandateValidator(MandateRegistry(_make_store()))
        budget = _make_budget(max_capital=10000.0)
        mandate = Mandate(
            mandate_id="m1",
            strategy="momentum",
            symbols=("BTCUSDT",),
            risk_budget=budget,
            created_at=datetime.now(timezone.utc),
        )

        # Under budget
        assert validator.check_mandate_capital(mandate, 5000.0)
        # Over budget
        assert not validator.check_mandate_capital(mandate, 15000.0)

    def test_check_mandate_daily_loss(self) -> None:
        validator = MandateValidator(MandateRegistry(_make_store()))
        budget = _make_budget(max_capital=10000.0, max_daily_loss=0.02)
        mandate = Mandate(
            mandate_id="m1",
            strategy="momentum",
            symbols=("BTCUSDT",),
            risk_budget=budget,
            created_at=datetime.now(timezone.utc),
        )

        # Within loss limit (2% of 10k = 200)
        assert validator.check_mandate_daily_loss(mandate, -100.0)
        # Exceeds loss limit
        assert not validator.check_mandate_daily_loss(mandate, -300.0)
