"""Tests for the portfolio exporter."""

from __future__ import annotations

from datetime import datetime, timezone

from aiswarm.integrations.portfolio_tracker.exporter import (
    PortfolioExporter,
    TrackerService,
)
from aiswarm.integrations.portfolio_tracker.formatters import (
    format_coingecko,
    format_debank,
    format_zapper,
)
from aiswarm.types.portfolio import PortfolioSnapshot, Position


def _make_snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        nav=100000.0,
        cash=80000.0,
        gross_exposure=0.2,
        net_exposure=0.15,
        positions=(
            Position(
                symbol="BTC/USDT",
                quantity=0.5,
                avg_price=50000.0,
                market_price=51000.0,
                strategy="momentum",
            ),
            Position(
                symbol="ETH/USDT",
                quantity=5.0,
                avg_price=3000.0,
                market_price=3100.0,
                strategy="funding_rate",
            ),
        ),
    )


class TestFormatters:
    def test_format_coingecko(self) -> None:
        snap = _make_snapshot()
        result = format_coingecko(snap)
        assert result["total_value_usd"] == 100000.0
        assert len(result["positions"]) == 2
        assert result["positions"][0]["quantity"] == 0.5

    def test_format_zapper(self) -> None:
        snap = _make_snapshot()
        result = format_zapper(snap)
        assert result["net_worth"] == 100000.0
        assert len(result["assets"]) == 2
        assert result["assets"][0]["token"] == "BTC/USDT"

    def test_format_debank(self) -> None:
        snap = _make_snapshot()
        result = format_debank(snap)
        assert result["total_usd_value"] == 100000.0
        assert len(result["token_list"]) == 2


class TestPortfolioExporter:
    def test_export_no_services(self) -> None:
        exporter = PortfolioExporter(services=[])
        results = exporter.export(_make_snapshot())
        assert results == []

    def test_export_single_service(self) -> None:
        exporter = PortfolioExporter(services=[TrackerService.COINGECKO])
        results = exporter.export(_make_snapshot())
        assert len(results) == 1
        assert results[0].success
        assert results[0].service == "coingecko"

    def test_export_multiple_services(self) -> None:
        exporter = PortfolioExporter(
            services=[TrackerService.COINGECKO, TrackerService.ZAPPER, TrackerService.DEBANK]
        )
        results = exporter.export(_make_snapshot())
        assert len(results) == 3
        assert all(r.success for r in results)

    def test_empty_positions(self) -> None:
        snap = PortfolioSnapshot(
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            nav=50000.0,
            cash=50000.0,
            gross_exposure=0.0,
            net_exposure=0.0,
            positions=(),
        )
        exporter = PortfolioExporter(services=[TrackerService.COINGECKO])
        results = exporter.export(snap)
        assert results[0].success
