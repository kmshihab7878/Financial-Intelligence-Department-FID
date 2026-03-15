"""Tests for the market data service."""

from __future__ import annotations

from aiswarm.execution.mcp_gateway import MockMCPGateway
from aiswarm.loop.market_data import MarketDataService


class TestMarketDataService:
    def test_fetch_symbol_data(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__aster__get_klines",
            {"data": [{"open": "100", "high": "110", "low": "90", "close": "105"}]},
        )
        gateway.set_response(
            "mcp__aster__get_funding_rate",
            {"fundingRate": "0.0001", "symbol": "BTCUSDT"},
        )

        svc = MarketDataService(gateway)
        data = svc.fetch_symbol_data("BTCUSDT")

        assert data.symbol == "BTCUSDT"
        assert data.klines_raw is not None
        assert data.funding_raw is not None
        assert data.ticker_raw is not None  # Default response
        assert data.orderbook_raw is not None  # Default response

    def test_fetch_handles_errors_gracefully(self) -> None:
        """If a tool call raises, returns None for that field."""

        class FailingGateway:
            def call_tool(self, tool_name: str, params: dict) -> dict:
                raise ConnectionError("network down")

        svc = MarketDataService(FailingGateway())  # type: ignore[arg-type]
        data = svc.fetch_symbol_data("BTCUSDT")

        assert data.symbol == "BTCUSDT"
        assert data.klines_raw is None
        assert data.funding_raw is None

    def test_build_agent_context(self) -> None:
        gateway = MockMCPGateway()
        svc = MarketDataService(gateway)
        data = svc.fetch_symbol_data("ETHUSDT")
        ctx = svc.build_agent_context(data)

        assert ctx["symbol"] == "ETHUSDT"
        assert "klines_data" in ctx
        assert "funding_data" in ctx

    def test_build_agent_context_no_data(self) -> None:
        """Context excludes keys when raw data is None."""

        class NullGateway:
            def call_tool(self, tool_name: str, params: dict) -> dict:
                raise RuntimeError("no data")

        svc = MarketDataService(NullGateway())  # type: ignore[arg-type]
        data = svc.fetch_symbol_data("BTCUSDT")
        ctx = svc.build_agent_context(data)

        assert ctx == {"symbol": "BTCUSDT"}

    def test_records_mcp_calls(self) -> None:
        gateway = MockMCPGateway()
        svc = MarketDataService(gateway)
        svc.fetch_symbol_data("BTCUSDT")

        tools = [c.tool_name for c in gateway.call_history]
        assert "mcp__aster__get_klines" in tools
        assert "mcp__aster__get_funding_rate" in tools
        assert "mcp__aster__get_ticker" in tools
        assert "mcp__aster__get_order_book" in tools

    def test_liquidity_score_default(self) -> None:
        gateway = MockMCPGateway()
        svc = MarketDataService(gateway)
        data = svc.fetch_symbol_data("BTCUSDT")
        # Default orderbook response won't parse to a real OrderBook
        score = svc.compute_liquidity_score(data)
        assert 0.0 <= score <= 1.0
