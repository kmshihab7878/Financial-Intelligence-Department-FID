"""Tests for the market data service."""

from __future__ import annotations

from aiswarm.exchange.providers.aster import AsterExchangeProvider
from aiswarm.execution.mcp_gateway import MockMCPGateway
from aiswarm.loop.market_data import MarketDataService


class TestMarketDataService:
    def test_fetch_symbol_data(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__aster__get_klines",
            [
                {
                    "openTime": 1700000000000,
                    "open": "100",
                    "high": "110",
                    "low": "90",
                    "close": "105",
                    "volume": "1000",
                }
            ],
        )
        gateway.set_response(
            "mcp__aster__get_funding_rate",
            {
                "symbol": "BTCUSDT",
                "lastFundingRate": "0.0001",
                "markPrice": "50000",
            },
        )
        gateway.set_response(
            "mcp__aster__get_ticker",
            {
                "symbol": "BTCUSDT",
                "lastPrice": "50000",
                "highPrice": "51000",
                "lowPrice": "49000",
                "volume": "1000",
                "priceChangePercent": "1.5",
            },
        )
        gateway.set_response(
            "mcp__aster__get_order_book",
            {
                "bids": [["50000", "1.0"]],
                "asks": [["50100", "1.0"]],
            },
        )

        provider = AsterExchangeProvider(gateway)
        svc = MarketDataService(provider)
        data = svc.fetch_symbol_data("BTCUSDT")

        assert data.symbol == "BTCUSDT"
        assert data.klines_raw is not None
        assert data.funding_raw is not None
        assert data.ticker_raw is not None
        assert data.orderbook_raw is not None

    def test_fetch_handles_errors_gracefully(self) -> None:
        """If provider calls raise, returns None for that field."""
        from unittest.mock import MagicMock

        provider = MagicMock()
        provider.get_klines.return_value = []
        provider.get_funding_rate.return_value = None
        provider.get_ticker.return_value = None
        provider.get_order_book.return_value = None

        svc = MarketDataService(provider)
        data = svc.fetch_symbol_data("BTCUSDT")

        assert data.symbol == "BTCUSDT"
        assert data.klines_raw is None  # empty list -> None
        assert data.funding_raw is None
        assert data.ticker_raw is None
        assert data.orderbook_raw is None

    def test_build_agent_context(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__aster__get_klines",
            [
                {
                    "openTime": 1700000000000,
                    "open": "100",
                    "high": "110",
                    "low": "90",
                    "close": "105",
                    "volume": "1000",
                }
            ],
        )
        gateway.set_response(
            "mcp__aster__get_funding_rate",
            {"symbol": "ETHUSDT", "lastFundingRate": "0.0001", "markPrice": "3000"},
        )
        gateway.set_response(
            "mcp__aster__get_ticker",
            {
                "symbol": "ETHUSDT",
                "lastPrice": "3000",
                "highPrice": "3100",
                "lowPrice": "2900",
                "volume": "500",
                "priceChangePercent": "2.0",
            },
        )
        gateway.set_response(
            "mcp__aster__get_order_book",
            {"bids": [["3000", "1.0"]], "asks": [["3010", "1.0"]]},
        )

        provider = AsterExchangeProvider(gateway)
        svc = MarketDataService(provider)
        data = svc.fetch_symbol_data("ETHUSDT")
        ctx = svc.build_agent_context(data)

        assert ctx["symbol"] == "ETHUSDT"
        assert "klines_data" in ctx
        assert "funding_data" in ctx

    def test_build_agent_context_no_data(self) -> None:
        """Context excludes keys when raw data is None."""
        from unittest.mock import MagicMock

        provider = MagicMock()
        provider.get_klines.return_value = []
        provider.get_funding_rate.return_value = None
        provider.get_ticker.return_value = None
        provider.get_order_book.return_value = None

        svc = MarketDataService(provider)
        data = svc.fetch_symbol_data("BTCUSDT")
        ctx = svc.build_agent_context(data)

        assert ctx == {"symbol": "BTCUSDT"}

    def test_records_mcp_calls(self) -> None:
        gateway = MockMCPGateway()
        provider = AsterExchangeProvider(gateway)
        svc = MarketDataService(provider)
        svc.fetch_symbol_data("BTCUSDT")

        tools = [c.tool_name for c in gateway.call_history]
        assert "mcp__aster__get_klines" in tools
        assert "mcp__aster__get_funding_rate" in tools
        assert "mcp__aster__get_ticker" in tools
        assert "mcp__aster__get_order_book" in tools

    def test_liquidity_score_default(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__aster__get_order_book",
            {"bids": [["50000", "1.0"]], "asks": [["50100", "1.0"]]},
        )
        provider = AsterExchangeProvider(gateway)
        svc = MarketDataService(provider)
        data = svc.fetch_symbol_data("BTCUSDT")
        score = svc.compute_liquidity_score(data)
        assert 0.0 <= score <= 1.0
