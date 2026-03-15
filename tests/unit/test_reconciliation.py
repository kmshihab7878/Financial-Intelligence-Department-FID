"""Tests for position reconciliation against Aster DEX."""

from __future__ import annotations

from datetime import datetime, timezone

from aiswarm.data.providers.aster import AccountBalance, ExchangePosition, TradeRecord
from aiswarm.monitoring.reconciliation import (
    PositionReconciler,
    ReconciliationStatus,
)
from aiswarm.types.portfolio import PortfolioSnapshot, Position


def _make_snapshot(
    positions: tuple[Position, ...] = (),
    nav: float = 100_000.0,
) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        timestamp=datetime.now(timezone.utc),
        nav=nav,
        cash=nav,
        gross_exposure=0.0,
        net_exposure=0.0,
        positions=positions,
    )


def _make_position(symbol: str = "BTCUSDT", quantity: float = 1.0) -> Position:
    return Position(
        symbol=symbol,
        quantity=quantity,
        avg_price=50000.0,
        market_price=50000.0,
        strategy="test",
    )


def _make_exchange_position(
    symbol: str = "BTCUSDT",
    quantity: float = 1.0,
) -> ExchangePosition:
    return ExchangePosition(
        symbol=symbol,
        side="LONG",
        quantity=quantity,
        entry_price=50000.0,
        mark_price=50000.0,
        unrealized_pnl=0.0,
        leverage=1,
        margin_mode="ISOLATED",
    )


class TestPositionReconciler:
    def test_matching_positions(self) -> None:
        reconciler = PositionReconciler(tolerance=0.001)
        snap = _make_snapshot(positions=(_make_position("BTCUSDT", 1.0),))
        exchange = [_make_exchange_position("BTCUSDT", 1.0)]

        results = reconciler.reconcile_positions(snap, exchange)
        assert len(results) == 1
        assert results[0].status == ReconciliationStatus.MATCH

    def test_quantity_mismatch(self) -> None:
        reconciler = PositionReconciler(tolerance=0.001)
        snap = _make_snapshot(positions=(_make_position("BTCUSDT", 1.0),))
        exchange = [_make_exchange_position("BTCUSDT", 1.5)]

        results = reconciler.reconcile_positions(snap, exchange)
        assert len(results) == 1
        assert results[0].status == ReconciliationStatus.MISMATCH

    def test_missing_exchange_position(self) -> None:
        reconciler = PositionReconciler(tolerance=0.001)
        snap = _make_snapshot(positions=(_make_position("BTCUSDT", 1.0),))
        exchange: list[ExchangePosition] = []

        results = reconciler.reconcile_positions(snap, exchange)
        assert len(results) == 1
        assert results[0].status == ReconciliationStatus.MISSING_EXCHANGE

    def test_missing_internal_position(self) -> None:
        reconciler = PositionReconciler(tolerance=0.001)
        snap = _make_snapshot(positions=())
        exchange = [_make_exchange_position("BTCUSDT", 1.0)]

        results = reconciler.reconcile_positions(snap, exchange)
        assert len(results) == 1
        assert results[0].status == ReconciliationStatus.MISSING_INTERNAL

    def test_no_snapshot_with_exchange_positions(self) -> None:
        reconciler = PositionReconciler(tolerance=0.001)
        exchange = [_make_exchange_position("BTCUSDT", 1.0)]

        results = reconciler.reconcile_positions(None, exchange)
        assert len(results) == 1
        assert results[0].status == ReconciliationStatus.MISSING_INTERNAL

    def test_no_snapshot_no_exchange(self) -> None:
        reconciler = PositionReconciler(tolerance=0.001)
        results = reconciler.reconcile_positions(None, [])
        assert len(results) == 0

    def test_balance_match(self) -> None:
        reconciler = PositionReconciler(tolerance=0.001)
        balance = AccountBalance(
            asset="USDT",
            total_balance=100_000.0,
            available_balance=90_000.0,
            unrealized_pnl=0.0,
            margin_balance=100_000.0,
        )
        result = reconciler.reconcile_balance(100_000.0, balance)
        assert result.status == ReconciliationStatus.MATCH

    def test_balance_mismatch(self) -> None:
        reconciler = PositionReconciler(tolerance=0.001)
        balance = AccountBalance(
            asset="USDT",
            total_balance=95_000.0,
            available_balance=90_000.0,
            unrealized_pnl=0.0,
            margin_balance=95_000.0,
        )
        result = reconciler.reconcile_balance(100_000.0, balance)
        assert result.status == ReconciliationStatus.MISMATCH

    def test_unauthorized_trade_detection(self) -> None:
        reconciler = PositionReconciler(tolerance=0.001)
        known_ids = {"trade_001", "trade_002"}
        exchange_trades = [
            TradeRecord(
                trade_id="trade_001",
                symbol="BTCUSDT",
                side="BUY",
                price=50000.0,
                quantity=1.0,
                commission=5.0,
                commission_asset="USDT",
                realized_pnl=0.0,
                timestamp=datetime.now(timezone.utc),
            ),
            TradeRecord(
                trade_id="trade_999",
                symbol="BTCUSDT",
                side="SELL",
                price=51000.0,
                quantity=0.5,
                commission=2.5,
                commission_asset="USDT",
                realized_pnl=0.0,
                timestamp=datetime.now(timezone.utc),
            ),
        ]

        results = reconciler.check_unauthorized_trades(known_ids, exchange_trades)
        assert len(results) == 1
        assert results[0].check_type == "unauthorized_trade"
        assert "trade_999" in results[0].message

    def test_full_reconciliation_pass(self) -> None:
        reconciler = PositionReconciler(tolerance=0.001)
        snap = _make_snapshot(positions=(_make_position("BTCUSDT", 1.0),), nav=100_000)
        exchange_pos = [_make_exchange_position("BTCUSDT", 1.0)]
        exchange_bal = AccountBalance(
            asset="USDT",
            total_balance=100_000.0,
            available_balance=90_000.0,
            unrealized_pnl=0.0,
            margin_balance=100_000.0,
        )

        report = reconciler.run_full_reconciliation(
            snap, exchange_pos, exchange_bal, exchange_trades=[], known_order_ids=set()
        )
        assert report.passed
        assert report.mismatches == 0

    def test_full_reconciliation_fail(self) -> None:
        reconciler = PositionReconciler(tolerance=0.001)
        snap = _make_snapshot(positions=(_make_position("BTCUSDT", 1.0),), nav=100_000)
        exchange_pos = [_make_exchange_position("BTCUSDT", 2.0)]  # mismatch

        report = reconciler.run_full_reconciliation(snap, exchange_pos)
        assert not report.passed
        assert report.mismatches > 0
