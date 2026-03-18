"""Tests for the CoinbaseExchangeProvider."""

from __future__ import annotations

import pytest

from aiswarm.exchange.provider import AssetClass
from aiswarm.exchange.providers.coinbase import (
    CoinbaseExchangeProvider,
    _normalize_order_response,
    normalize_symbol,
    parse_balance,
    parse_ohlcv,
    parse_order_book,
    parse_ticker,
    parse_trade,
    to_canonical_symbol,
)
from aiswarm.execution.mcp_gateway import MockMCPGateway


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestCoinbaseProviderProperties:
    def test_exchange_id(self) -> None:
        provider = CoinbaseExchangeProvider(MockMCPGateway())
        assert provider.exchange_id == "coinbase"

    def test_supported_asset_classes_spot_only(self) -> None:
        provider = CoinbaseExchangeProvider(MockMCPGateway())
        assert AssetClass.SPOT in provider.supported_asset_classes
        assert AssetClass.FUTURES not in provider.supported_asset_classes
        assert AssetClass.OPTIONS not in provider.supported_asset_classes


# ---------------------------------------------------------------------------
# Symbol normalization
# ---------------------------------------------------------------------------


class TestCoinbaseSymbolNormalization:
    def test_normalize_canonical_usdt(self) -> None:
        assert normalize_symbol("BTC/USDT") == "BTC-USD"

    def test_normalize_canonical_usd(self) -> None:
        assert normalize_symbol("BTC/USD") == "BTC-USD"

    def test_normalize_canonical_usdc(self) -> None:
        assert normalize_symbol("ETH/USDC") == "ETH-USD"

    def test_normalize_already_coinbase_format(self) -> None:
        assert normalize_symbol("BTC-USD") == "BTC-USD"

    def test_normalize_concatenated_usdt(self) -> None:
        assert normalize_symbol("BTCUSDT") == "BTC-USD"

    def test_normalize_concatenated_usd(self) -> None:
        assert normalize_symbol("BTCUSD") == "BTC-USD"

    def test_normalize_lowercase(self) -> None:
        assert normalize_symbol("btc/usdt") == "BTC-USD"

    def test_normalize_eth(self) -> None:
        assert normalize_symbol("ETH/USDT") == "ETH-USD"

    def test_normalize_sol(self) -> None:
        assert normalize_symbol("SOL/USD") == "SOL-USD"

    def test_normalize_unknown_quote(self) -> None:
        """Unknown quote currencies pass through without alias mapping."""
        assert normalize_symbol("BTC/EUR") == "BTC-EUR"

    def test_normalize_via_provider(self) -> None:
        provider = CoinbaseExchangeProvider(MockMCPGateway())
        assert provider.normalize_symbol("BTC/USDT") == "BTC-USD"

    def test_to_canonical_basic(self) -> None:
        assert to_canonical_symbol("BTC-USD") == "BTC/USD"

    def test_to_canonical_eth(self) -> None:
        assert to_canonical_symbol("ETH-USD") == "ETH/USD"

    def test_to_canonical_no_dash(self) -> None:
        """Non-dash symbols pass through unchanged."""
        assert to_canonical_symbol("BTCUSD") == "BTCUSD"

    def test_to_canonical_via_provider(self) -> None:
        provider = CoinbaseExchangeProvider(MockMCPGateway())
        assert provider.to_canonical_symbol("BTC-USD") == "BTC/USD"


# ---------------------------------------------------------------------------
# Parser unit tests (standalone functions)
# ---------------------------------------------------------------------------


class TestCoinbaseParsers:
    def test_parse_ohlcv(self) -> None:
        raw = {
            "start": 1700000000,
            "open": "50000",
            "high": "51000",
            "low": "49000",
            "close": "50500",
            "volume": "100",
        }
        candle = parse_ohlcv(raw, "BTC-USD")
        assert candle.open == 50000.0
        assert candle.high == 51000.0
        assert candle.low == 49000.0
        assert candle.close == 50500.0
        assert candle.volume == 100.0
        assert candle.symbol == "BTC/USD"

    def test_parse_ohlcv_millisecond_timestamp(self) -> None:
        raw = {
            "start": 1700000000000,
            "open": "1",
            "high": "2",
            "low": "0.5",
            "close": "1.5",
            "volume": "10",
        }
        candle = parse_ohlcv(raw, "ETH-USD")
        assert candle.timestamp.year > 2000  # Converted from ms to s correctly

    def test_parse_ticker(self) -> None:
        raw = {
            "product_id": "BTC-USD",
            "price": "50000",
            "high_24h": "51000",
            "low_24h": "49000",
            "volume_24h": "1000",
            "price_change_pct": "2.5",
        }
        ticker = parse_ticker(raw)
        assert ticker.symbol == "BTC/USD"
        assert ticker.last_price == 50000.0
        assert ticker.high_24h == 51000.0
        assert ticker.low_24h == 49000.0
        assert ticker.volume_24h == 1000.0
        assert ticker.price_change_pct == 2.5

    def test_parse_order_book_dict_levels(self) -> None:
        raw = {
            "bids": [
                {"price": "50000", "size": "1.0"},
                {"price": "49900", "size": "2.0"},
            ],
            "asks": [
                {"price": "50100", "size": "0.5"},
            ],
        }
        ob = parse_order_book(raw, "BTC-USD")
        assert ob.symbol == "BTC/USD"
        assert len(ob.bids) == 2
        assert len(ob.asks) == 1
        assert ob.bids[0].price == 50000.0
        assert ob.bids[0].quantity == 1.0
        assert ob.bids[1].price == 49900.0
        assert ob.asks[0].price == 50100.0
        assert ob.asks[0].quantity == 0.5
        assert ob.spread == pytest.approx(100.0)

    def test_parse_balance(self) -> None:
        raw = {"currency": "USD", "balance": "100000", "available": "80000"}
        bal = parse_balance(raw)
        assert bal.total_balance == 100000.0
        assert bal.available_balance == 80000.0
        assert bal.unrealized_pnl == 0.0
        assert bal.margin_balance == 0.0
        assert bal.asset == "USD"

    def test_parse_trade(self) -> None:
        raw = {
            "trade_id": "T1",
            "product_id": "BTC-USD",
            "side": "buy",
            "price": "50000",
            "size": "0.1",
            "fee": "5",
            "fee_currency": "USD",
            "order_id": "ORD1",
            "time": 1700000000,
        }
        trade = parse_trade(raw)
        assert trade.trade_id == "T1"
        assert trade.symbol == "BTC/USD"
        assert trade.side == "BUY"
        assert trade.price == 50000.0
        assert trade.quantity == 0.1
        assert trade.commission == 5.0
        assert trade.commission_asset == "USD"
        assert trade.realized_pnl == 0.0
        assert trade.order_id == "ORD1"

    def test_parse_trade_iso_timestamp(self) -> None:
        raw = {
            "trade_id": "T2",
            "product_id": "ETH-USD",
            "side": "sell",
            "price": "3000",
            "size": "1.0",
            "fee": "3",
            "time": "2024-01-15T10:30:00Z",
        }
        trade = parse_trade(raw)
        assert trade.trade_id == "T2"
        assert trade.timestamp.year == 2024

    def test_parse_trade_missing_time(self) -> None:
        raw = {
            "trade_id": "T3",
            "product_id": "SOL-USD",
            "side": "buy",
            "price": "100",
            "size": "10",
            "fee": "1",
        }
        trade = parse_trade(raw)
        assert trade.trade_id == "T3"
        # Timestamp defaults to now, just verify it's set
        assert trade.timestamp is not None

    def test_normalize_order_response(self) -> None:
        raw = {"id": "abc123", "product_id": "BTC-USD", "size": "0.1", "status": "pending"}
        normalized = _normalize_order_response(raw)
        assert normalized["orderId"] == "abc123"
        assert normalized["symbol"] == "BTC-USD"
        assert normalized["quantity"] == "0.1"
        # Original keys preserved
        assert normalized["id"] == "abc123"
        assert normalized["product_id"] == "BTC-USD"

    def test_normalize_order_response_already_has_order_id(self) -> None:
        raw = {"orderId": "existing", "id": "abc123", "product_id": "BTC-USD"}
        normalized = _normalize_order_response(raw)
        assert normalized["orderId"] == "existing"  # Not overwritten


# ---------------------------------------------------------------------------
# Market Data (via provider with MockMCPGateway)
# ---------------------------------------------------------------------------


class TestCoinbaseMarketData:
    def test_get_klines(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__coinbase__get_klines",
            [
                {
                    "start": 1700000000,
                    "open": "50000",
                    "high": "51000",
                    "low": "49000",
                    "close": "50500",
                    "volume": "100",
                },
            ],
        )
        provider = CoinbaseExchangeProvider(gateway)
        klines = provider.get_klines("BTC/USDT", "1h", 100)

        assert len(klines) == 1
        assert klines[0].open == 50000.0
        assert klines[0].close == 50500.0
        assert klines[0].symbol == "BTC/USD"

    def test_get_klines_wrapped_in_candles_key(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__coinbase__get_klines",
            {
                "candles": [
                    {
                        "start": 1700000000,
                        "open": "60000",
                        "high": "61000",
                        "low": "59000",
                        "close": "60500",
                        "volume": "200",
                    },
                ]
            },
        )
        provider = CoinbaseExchangeProvider(gateway)
        klines = provider.get_klines("BTC-USD", "1h", 50)

        assert len(klines) == 1
        assert klines[0].open == 60000.0

    def test_get_klines_tool_name_and_params(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response("mcp__coinbase__get_klines", [])
        provider = CoinbaseExchangeProvider(gateway)
        provider.get_klines("ETH/USDT", "15m", 200)

        call = gateway.call_history[-1]
        assert call.tool_name == "mcp__coinbase__get_klines"
        assert call.params["product_id"] == "ETH-USD"
        assert call.params["granularity"] == "15m"
        assert call.params["limit"] == 200

    def test_get_klines_error_returns_empty(self) -> None:
        class FailGateway:
            def call_tool(self, tool_name: str, params: dict) -> dict:  # type: ignore[type-arg]
                raise ConnectionError("down")

        provider = CoinbaseExchangeProvider(FailGateway())  # type: ignore[arg-type]
        assert provider.get_klines("BTC-USD") == []

    def test_get_ticker(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__coinbase__get_ticker",
            {
                "product_id": "BTC-USD",
                "price": "50000",
                "high_24h": "51000",
                "low_24h": "49000",
                "volume_24h": "1000",
                "price_change_pct": "2.0",
            },
        )
        provider = CoinbaseExchangeProvider(gateway)
        ticker = provider.get_ticker("BTC/USDT")

        assert ticker is not None
        assert ticker.symbol == "BTC/USD"
        assert ticker.last_price == 50000.0
        assert ticker.volume_24h == 1000.0
        assert ticker.price_change_pct == 2.0

    def test_get_ticker_tool_params(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__coinbase__get_ticker", {"product_id": "ETH-USD", "price": "3000"}
        )
        provider = CoinbaseExchangeProvider(gateway)
        provider.get_ticker("ETH/USDT")

        call = gateway.call_history[-1]
        assert call.tool_name == "mcp__coinbase__get_ticker"
        assert call.params["product_id"] == "ETH-USD"

    def test_get_ticker_error_returns_none(self) -> None:
        class FailGateway:
            def call_tool(self, tool_name: str, params: dict) -> dict:  # type: ignore[type-arg]
                raise ConnectionError("down")

        provider = CoinbaseExchangeProvider(FailGateway())  # type: ignore[arg-type]
        assert provider.get_ticker("BTC-USD") is None

    def test_get_order_book(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__coinbase__get_order_book",
            {
                "bids": [{"price": "50000", "size": "1.0"}, {"price": "49900", "size": "2.0"}],
                "asks": [{"price": "50100", "size": "0.5"}],
            },
        )
        provider = CoinbaseExchangeProvider(gateway)
        ob = provider.get_order_book("BTC/USDT")

        assert ob is not None
        assert ob.symbol == "BTC/USD"
        assert len(ob.bids) == 2
        assert len(ob.asks) == 1
        assert ob.bids[0].price == 50000.0
        assert ob.bids[0].quantity == 1.0
        assert ob.asks[0].price == 50100.0
        assert ob.spread == pytest.approx(100.0)

    def test_get_order_book_error_returns_none(self) -> None:
        class FailGateway:
            def call_tool(self, tool_name: str, params: dict) -> dict:  # type: ignore[type-arg]
                raise ConnectionError("down")

        provider = CoinbaseExchangeProvider(FailGateway())  # type: ignore[arg-type]
        assert provider.get_order_book("BTC-USD") is None

    def test_get_funding_rate_returns_none(self) -> None:
        """Coinbase spot has no funding rates."""
        provider = CoinbaseExchangeProvider(MockMCPGateway())
        assert provider.get_funding_rate("BTC-USD") is None


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------


class TestCoinbaseAccount:
    def test_get_balance(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__coinbase__get_balance",
            {"currency": "USD", "balance": "100000", "available": "80000"},
        )
        provider = CoinbaseExchangeProvider(gateway)
        bal = provider.get_balance()

        assert bal is not None
        assert bal.total_balance == 100000.0
        assert bal.available_balance == 80000.0
        assert bal.unrealized_pnl == 0.0
        assert bal.asset == "USD"

    def test_get_balance_wrapped_in_data(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__coinbase__get_balance",
            {
                "data": [
                    {"currency": "USD", "balance": "50000", "available": "40000"},
                ]
            },
        )
        provider = CoinbaseExchangeProvider(gateway)
        bal = provider.get_balance()

        assert bal is not None
        assert bal.total_balance == 50000.0
        assert bal.available_balance == 40000.0

    def test_get_balance_error_returns_none(self) -> None:
        class FailGateway:
            def call_tool(self, tool_name: str, params: dict) -> dict:  # type: ignore[type-arg]
                raise ConnectionError("down")

        provider = CoinbaseExchangeProvider(FailGateway())  # type: ignore[arg-type]
        assert provider.get_balance() is None

    def test_get_positions_returns_empty(self) -> None:
        """Coinbase spot has no positions."""
        provider = CoinbaseExchangeProvider(MockMCPGateway())
        assert provider.get_positions() == []


# ---------------------------------------------------------------------------
# Trading
# ---------------------------------------------------------------------------


class TestCoinbaseTrading:
    def test_place_order(self) -> None:
        gateway = MockMCPGateway()
        provider = CoinbaseExchangeProvider(gateway)

        result = provider.place_order(
            symbol="BTC/USDT",
            side="BUY",
            quantity=0.1,
            order_type="MARKET",
            venue="spot",
        )

        assert "orderId" in result
        call = gateway.call_history[-1]
        assert call.tool_name == "mcp__coinbase__create_order"
        assert call.params["product_id"] == "BTC-USD"
        assert call.params["side"] == "buy"
        assert call.params["size"] == "0.1"
        assert call.params["order_type"] == "market"

    def test_place_limit_order_with_price(self) -> None:
        gateway = MockMCPGateway()
        provider = CoinbaseExchangeProvider(gateway)

        result = provider.place_order(
            symbol="ETH/USD",
            side="SELL",
            quantity=1.5,
            order_type="LIMIT",
            price=3000.0,
            venue="spot",
        )

        assert "orderId" in result
        call = gateway.call_history[-1]
        assert call.params["price"] == "3000.0"
        assert call.params["time_in_force"] == "GTC"

    def test_place_order_normalizes_response(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__coinbase__create_order",
            {"id": "cb-order-001", "product_id": "BTC-USD", "size": "0.1", "status": "pending"},
        )
        provider = CoinbaseExchangeProvider(gateway)

        result = provider.place_order(
            symbol="BTC-USD",
            side="BUY",
            quantity=0.1,
            venue="spot",
        )

        assert result["orderId"] == "cb-order-001"
        assert result["symbol"] == "BTC-USD"
        assert result["quantity"] == "0.1"

    def test_place_order_futures_venue_raises(self) -> None:
        provider = CoinbaseExchangeProvider(MockMCPGateway())
        with pytest.raises(NotImplementedError, match="spot venue"):
            provider.place_order(
                symbol="BTC-USD",
                side="BUY",
                quantity=0.1,
                venue="futures",
            )

    def test_cancel_order(self) -> None:
        gateway = MockMCPGateway()
        provider = CoinbaseExchangeProvider(gateway)

        provider.cancel_order("BTC/USDT", "cb-order-001")
        call = gateway.call_history[-1]
        assert call.tool_name == "mcp__coinbase__cancel_order"
        assert call.params["product_id"] == "BTC-USD"
        assert call.params["order_id"] == "cb-order-001"

    def test_cancel_all_orders(self) -> None:
        gateway = MockMCPGateway()
        provider = CoinbaseExchangeProvider(gateway)

        provider.cancel_all_orders("BTC/USDT")
        call = gateway.call_history[-1]
        assert call.tool_name == "mcp__coinbase__cancel_all_orders"
        assert call.params["product_id"] == "BTC-USD"

    def test_get_order_status(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__coinbase__get_order",
            {"id": "cb-order-001", "product_id": "BTC-USD", "status": "done"},
        )
        provider = CoinbaseExchangeProvider(gateway)

        result = provider.get_order_status("BTC-USD", "cb-order-001")
        assert result["orderId"] == "cb-order-001"
        assert result["status"] == "done"

    def test_get_my_trades(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__coinbase__get_my_trades",
            [
                {
                    "trade_id": "T1",
                    "product_id": "BTC-USD",
                    "side": "buy",
                    "price": "50000",
                    "size": "0.1",
                    "fee": "5",
                    "fee_currency": "USD",
                    "order_id": "ORD1",
                    "time": 1700000000,
                }
            ],
        )
        provider = CoinbaseExchangeProvider(gateway)
        trades = provider.get_my_trades("BTC/USDT")

        assert len(trades) == 1
        assert trades[0].trade_id == "T1"
        assert trades[0].symbol == "BTC/USD"
        assert trades[0].side == "BUY"
        assert trades[0].price == 50000.0
        assert trades[0].quantity == 0.1
        assert trades[0].commission == 5.0

    def test_get_my_trades_wrapped_in_fills(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__coinbase__get_my_trades",
            {
                "fills": [
                    {
                        "trade_id": "T2",
                        "product_id": "ETH-USD",
                        "side": "sell",
                        "price": "3000",
                        "size": "1.0",
                        "fee": "3",
                        "time": 1700000000,
                    }
                ]
            },
        )
        provider = CoinbaseExchangeProvider(gateway)
        trades = provider.get_my_trades("ETH-USD")

        assert len(trades) == 1
        assert trades[0].trade_id == "T2"

    def test_get_my_trades_error_returns_empty(self) -> None:
        class FailGateway:
            def call_tool(self, tool_name: str, params: dict) -> dict:  # type: ignore[type-arg]
                raise ConnectionError("down")

        provider = CoinbaseExchangeProvider(FailGateway())  # type: ignore[arg-type]
        assert provider.get_my_trades("BTC-USD") == []

    def test_get_my_trades_tool_params(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response("mcp__coinbase__get_my_trades", [])
        provider = CoinbaseExchangeProvider(gateway)
        provider.get_my_trades("SOL/USD")

        call = gateway.call_history[-1]
        assert call.tool_name == "mcp__coinbase__get_my_trades"
        assert call.params["product_id"] == "SOL-USD"


# ---------------------------------------------------------------------------
# Leverage / Margin (unsupported)
# ---------------------------------------------------------------------------


class TestCoinbaseLeverageMargin:
    def test_set_leverage_raises(self) -> None:
        provider = CoinbaseExchangeProvider(MockMCPGateway())
        with pytest.raises(NotImplementedError, match="set_leverage"):
            provider.set_leverage("BTC-USD", 5)

    def test_set_margin_mode_raises(self) -> None:
        provider = CoinbaseExchangeProvider(MockMCPGateway())
        with pytest.raises(NotImplementedError, match="set_margin_mode"):
            provider.set_margin_mode("BTC-USD", "ISOLATED")


# ---------------------------------------------------------------------------
# Tool name constants
# ---------------------------------------------------------------------------


class TestCoinbaseToolNames:
    """Verify that the correct MCP tool names are used for each operation."""

    def test_klines_tool_name(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response("mcp__coinbase__get_klines", [])
        provider = CoinbaseExchangeProvider(gateway)
        provider.get_klines("BTC-USD")
        assert gateway.call_history[-1].tool_name == "mcp__coinbase__get_klines"

    def test_ticker_tool_name(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__coinbase__get_ticker", {"product_id": "BTC-USD", "price": "50000"}
        )
        provider = CoinbaseExchangeProvider(gateway)
        provider.get_ticker("BTC-USD")
        assert gateway.call_history[-1].tool_name == "mcp__coinbase__get_ticker"

    def test_order_book_tool_name(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response("mcp__coinbase__get_order_book", {"bids": [], "asks": []})
        provider = CoinbaseExchangeProvider(gateway)
        provider.get_order_book("BTC-USD")
        assert gateway.call_history[-1].tool_name == "mcp__coinbase__get_order_book"

    def test_balance_tool_name(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__coinbase__get_balance",
            {"currency": "USD", "balance": "1000", "available": "1000"},
        )
        provider = CoinbaseExchangeProvider(gateway)
        provider.get_balance()
        assert gateway.call_history[-1].tool_name == "mcp__coinbase__get_balance"

    def test_create_order_tool_name(self) -> None:
        gateway = MockMCPGateway()
        provider = CoinbaseExchangeProvider(gateway)
        provider.place_order("BTC-USD", "BUY", 0.1, venue="spot")
        assert gateway.call_history[-1].tool_name == "mcp__coinbase__create_order"

    def test_cancel_order_tool_name(self) -> None:
        gateway = MockMCPGateway()
        provider = CoinbaseExchangeProvider(gateway)
        provider.cancel_order("BTC-USD", "ORD1")
        assert gateway.call_history[-1].tool_name == "mcp__coinbase__cancel_order"

    def test_cancel_all_orders_tool_name(self) -> None:
        gateway = MockMCPGateway()
        provider = CoinbaseExchangeProvider(gateway)
        provider.cancel_all_orders("BTC-USD")
        assert gateway.call_history[-1].tool_name == "mcp__coinbase__cancel_all_orders"

    def test_get_order_tool_name(self) -> None:
        gateway = MockMCPGateway()
        provider = CoinbaseExchangeProvider(gateway)
        provider.get_order_status("BTC-USD", "ORD1")
        assert gateway.call_history[-1].tool_name == "mcp__coinbase__get_order"

    def test_get_my_trades_tool_name(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response("mcp__coinbase__get_my_trades", [])
        provider = CoinbaseExchangeProvider(gateway)
        provider.get_my_trades("BTC-USD")
        assert gateway.call_history[-1].tool_name == "mcp__coinbase__get_my_trades"
