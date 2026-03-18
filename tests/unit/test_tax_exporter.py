"""Tests for the tax exporter."""

from __future__ import annotations

import tempfile

from aiswarm.data.event_store import EventStore
from aiswarm.integrations.tax.exporter import TaxExporter, TaxFormat
from aiswarm.integrations.tax.formatters import (
    format_cointracker_row,
    format_csv_row,
    format_koinly_row,
)


def _make_event_store_with_fills() -> EventStore:
    """Create an EventStore with some fill events for testing."""
    es = EventStore(tempfile.mktemp(suffix=".db"))
    # Simulate fill events
    es.append(
        "order_filled",
        {
            "order_id": "o1",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "fill_price": 50000.0,
            "fill_quantity": 0.1,
            "commission": 5.0,
            "commission_asset": "USDT",
            "realized_pnl": 0.0,
        },
    )
    es.append(
        "order_filled",
        {
            "order_id": "o2",
            "symbol": "ETHUSDT",
            "side": "SELL",
            "fill_price": 3000.0,
            "fill_quantity": 1.0,
            "commission": 3.0,
            "commission_asset": "USDT",
            "realized_pnl": 150.0,
        },
    )
    return es


class TestFormatters:
    def test_format_csv_row_buy(self) -> None:
        row = format_csv_row(
            "2024-01-01T00:00:00",
            {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "fill_price": 50000.0,
                "fill_quantity": 0.1,
                "commission": "5.0",
            },
        )
        assert row[0] == "2024-01-01T00:00:00"
        assert row[2] == "BTCUSDT"
        assert row[3] == "BUY"
        assert row[4] == "0.1"

    def test_format_koinly_row_buy(self) -> None:
        row = format_koinly_row(
            "2024-01-01T00:00:00",
            {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "fill_price": 50000.0,
                "fill_quantity": 0.1,
                "commission": "5.0",
            },
        )
        # Buy: sent USDT, received BTC
        assert row[0] == "2024-01-01T00:00:00"
        assert row[3] == "0.1"  # received amount
        assert row[4] == "BTC"  # received currency

    def test_format_koinly_row_sell(self) -> None:
        row = format_koinly_row(
            "2024-01-01T00:00:00",
            {
                "symbol": "ETHUSDT",
                "side": "SELL",
                "fill_price": 3000.0,
                "fill_quantity": 1.0,
                "commission": "3.0",
            },
        )
        # Sell: sent ETH, received USDT
        assert row[0] == "2024-01-01T00:00:00"
        assert row[1] == "1.0"  # sent amount
        assert row[2] == "ETH"  # sent currency

    def test_format_cointracker_row_buy(self) -> None:
        row = format_cointracker_row(
            "2024-01-01T00:00:00",
            {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "fill_price": 50000.0,
                "fill_quantity": 0.1,
            },
        )
        assert row[1] == "Buy"
        assert row[2] == "0.1"  # received qty
        assert row[3] == "BTC"  # received currency

    def test_format_cointracker_row_sell(self) -> None:
        row = format_cointracker_row(
            "2024-01-01T00:00:00",
            {
                "symbol": "ETHUSDT",
                "side": "SELL",
                "fill_price": 3000.0,
                "fill_quantity": 1.0,
            },
        )
        assert row[1] == "Sell"
        assert row[4] == "1.0"  # sent qty
        assert row[5] == "ETH"  # sent currency


class TestTaxExporter:
    def test_export_csv(self) -> None:
        es = _make_event_store_with_fills()
        exporter = TaxExporter(es)
        result = exporter.export(TaxFormat.CSV)

        assert result.success
        assert result.rows == 2
        assert "BTCUSDT" in result.content
        assert "ETHUSDT" in result.content

    def test_export_koinly(self) -> None:
        es = _make_event_store_with_fills()
        exporter = TaxExporter(es)
        result = exporter.export(TaxFormat.KOINLY)

        assert result.success
        assert result.rows == 2
        assert "Sent Amount" in result.content  # Koinly header

    def test_export_cointracker(self) -> None:
        es = _make_event_store_with_fills()
        exporter = TaxExporter(es)
        result = exporter.export(TaxFormat.COINTRACKER)

        assert result.success
        assert result.rows == 2
        assert "Received Quantity" in result.content  # CoinTracker header

    def test_export_empty_store(self) -> None:
        es = EventStore(tempfile.mktemp(suffix=".db"))
        exporter = TaxExporter(es)
        result = exporter.export(TaxFormat.CSV)

        assert result.success
        assert result.rows == 0
        # Should still have headers
        assert "date" in result.content
