"""Tests for the IBExchangeProvider."""

from __future__ import annotations

import pytest

from aiswarm.exchange.provider import AssetClass
from aiswarm.exchange.providers.ib import IBExchangeProvider
from aiswarm.execution.mcp_gateway import MockMCPGateway


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestIBProviderProperties:
    def test_exchange_id(self) -> None:
        provider = IBExchangeProvider(MockMCPGateway())
        assert provider.exchange_id == "ib"

    def test_supported_asset_classes(self) -> None:
        provider = IBExchangeProvider(MockMCPGateway())
        classes = provider.supported_asset_classes
        assert AssetClass.STOCKS in classes
        assert AssetClass.OPTIONS in classes
        assert AssetClass.FUTURES in classes
        assert AssetClass.FOREX in classes
        assert AssetClass.SPOT not in classes

    def test_account_id_stored(self) -> None:
        provider = IBExchangeProvider(MockMCPGateway(), account_id="U9999")
        assert provider.account_id == "U9999"


# ---------------------------------------------------------------------------
# Symbol normalization
# ---------------------------------------------------------------------------


class TestIBSymbolNormalization:
    def test_normalize_stock_ticker(self) -> None:
        provider = IBExchangeProvider(MockMCPGateway())
        assert provider.normalize_symbol("AAPL") == "AAPL"

    def test_normalize_crypto_slash(self) -> None:
        provider = IBExchangeProvider(MockMCPGateway())
        assert provider.normalize_symbol("BTC/USD") == "BTC"

    def test_normalize_forex_slash(self) -> None:
        provider = IBExchangeProvider(MockMCPGateway())
        assert provider.normalize_symbol("EUR/USD") == "EUR"

    def test_to_canonical_stock(self) -> None:
        provider = IBExchangeProvider(MockMCPGateway())
        assert provider.to_canonical_symbol("AAPL") == "AAPL"

    def test_to_canonical_crypto(self) -> None:
        provider = IBExchangeProvider(MockMCPGateway())
        assert provider.to_canonical_symbol("BTCUSD") == "BTC/USD"

    def test_to_canonical_eth(self) -> None:
        provider = IBExchangeProvider(MockMCPGateway())
        assert provider.to_canonical_symbol("ETHUSD") == "ETH/USD"

    def test_to_canonical_non_crypto_usd_suffix(self) -> None:
        """A stock like 'MSGUSD' should NOT be treated as crypto."""
        provider = IBExchangeProvider(MockMCPGateway())
        # MSGUSD is not a known crypto ticker, stays as-is
        assert provider.to_canonical_symbol("MSGUSD") == "MSGUSD"

    def test_to_canonical_spy(self) -> None:
        provider = IBExchangeProvider(MockMCPGateway())
        assert provider.to_canonical_symbol("SPY") == "SPY"


# ---------------------------------------------------------------------------
# Funding rate (unsupported)
# ---------------------------------------------------------------------------


class TestIBFundingRate:
    def test_get_funding_rate_returns_none(self) -> None:
        provider = IBExchangeProvider(MockMCPGateway())
        assert provider.get_funding_rate("AAPL") is None

    def test_get_funding_rate_returns_none_for_any_symbol(self) -> None:
        provider = IBExchangeProvider(MockMCPGateway())
        assert provider.get_funding_rate("BTC/USD") is None
        assert provider.get_funding_rate("ES") is None


# ---------------------------------------------------------------------------
# Leverage/Margin (unsupported)
# ---------------------------------------------------------------------------


class TestIBLeverageMargin:
    def test_set_leverage_raises(self) -> None:
        provider = IBExchangeProvider(MockMCPGateway())
        with pytest.raises(NotImplementedError, match="ib does not support set_leverage"):
            provider.set_leverage("AAPL", 5)

    def test_set_margin_mode_raises(self) -> None:
        provider = IBExchangeProvider(MockMCPGateway())
        with pytest.raises(NotImplementedError, match="ib does not support set_margin_mode"):
            provider.set_margin_mode("AAPL", "ISOLATED")


# ---------------------------------------------------------------------------
# Order placement
# ---------------------------------------------------------------------------


class TestIBOrderPlacement:
    def test_place_market_order(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__ib__create_order",
            {"orderId": 12345, "orderStatus": "Submitted", "symbol": "AAPL"},
        )
        provider = IBExchangeProvider(gateway, account_id="U1234")

        result = provider.place_order(
            symbol="AAPL",
            side="BUY",
            quantity=100,
            order_type="MARKET",
            venue="stocks",
        )

        assert result["orderId"] == "12345"  # numeric -> string
        assert result["orderStatus"] == "Submitted"
        assert gateway.call_history[-1].tool_name == "mcp__ib__create_order"

        params = gateway.call_history[-1].params
        assert params["symbol"] == "AAPL"
        assert params["side"] == "BUY"
        assert params["quantity"] == 100
        assert params["orderType"] == "MARKET"
        assert params["secType"] == "STK"
        assert params["accountId"] == "U1234"

    def test_place_limit_order_with_price(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__ib__create_order",
            {"orderId": 99, "orderStatus": "PreSubmitted", "symbol": "AAPL"},
        )
        provider = IBExchangeProvider(gateway, account_id="U1234")

        result = provider.place_order(
            symbol="AAPL",
            side="SELL",
            quantity=50,
            order_type="LIMIT",
            price=155.50,
            venue="stocks",
        )

        assert result["orderId"] == "99"
        params = gateway.call_history[-1].params
        assert params["price"] == 155.50
        assert params["tif"] == "GTC"

    def test_place_futures_order_sec_type(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__ib__create_order",
            {"orderId": 200, "orderStatus": "Submitted", "symbol": "ES"},
        )
        provider = IBExchangeProvider(gateway)

        provider.place_order(
            symbol="ES",
            side="BUY",
            quantity=1,
            venue="futures",
        )

        params = gateway.call_history[-1].params
        assert params["secType"] == "FUT"

    def test_place_forex_order_sec_type(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__ib__create_order",
            {"orderId": 300, "orderStatus": "Submitted", "symbol": "EUR"},
        )
        provider = IBExchangeProvider(gateway)

        provider.place_order(
            symbol="EUR/USD",
            side="BUY",
            quantity=100000,
            venue="forex",
        )

        params = gateway.call_history[-1].params
        assert params["secType"] == "CASH"
        assert params["symbol"] == "EUR"

    def test_place_order_with_con_id(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__ib__create_order",
            {"orderId": 400, "orderStatus": "Submitted", "symbol": "AAPL"},
        )
        provider = IBExchangeProvider(gateway)

        provider.place_order(
            symbol="AAPL",
            side="BUY",
            quantity=10,
            venue="stocks",
            conId=265598,
        )

        params = gateway.call_history[-1].params
        assert params["conId"] == 265598

    def test_place_order_without_account_id(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__ib__create_order",
            {"orderId": 500, "orderStatus": "Submitted", "symbol": "AAPL"},
        )
        provider = IBExchangeProvider(gateway)  # no account_id

        provider.place_order(symbol="AAPL", side="BUY", quantity=10)
        params = gateway.call_history[-1].params
        assert "accountId" not in params


# ---------------------------------------------------------------------------
# Order cancellation
# ---------------------------------------------------------------------------


class TestIBOrderCancellation:
    def test_cancel_order(self) -> None:
        gateway = MockMCPGateway()
        provider = IBExchangeProvider(gateway, account_id="U1234")

        provider.cancel_order("AAPL", "12345")

        assert gateway.call_history[-1].tool_name == "mcp__ib__cancel_order"
        params = gateway.call_history[-1].params
        assert params["symbol"] == "AAPL"
        assert params["orderId"] == "12345"
        assert params["accountId"] == "U1234"

    def test_cancel_all_orders(self) -> None:
        gateway = MockMCPGateway()
        provider = IBExchangeProvider(gateway, account_id="U1234")

        provider.cancel_all_orders("AAPL")

        assert gateway.call_history[-1].tool_name == "mcp__ib__cancel_all_orders"
        params = gateway.call_history[-1].params
        assert params["symbol"] == "AAPL"


# ---------------------------------------------------------------------------
# Position parsing
# ---------------------------------------------------------------------------


class TestIBPositionParsing:
    def test_long_position(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__ib__get_positions",
            [
                {
                    "conid": 265598,
                    "symbol": "AAPL",
                    "position": 100,
                    "avgCost": 150.0,
                    "mktPrice": 155.0,
                    "unrealizedPnl": 500.0,
                }
            ],
        )
        provider = IBExchangeProvider(gateway)
        positions = provider.get_positions()

        assert len(positions) == 1
        pos = positions[0]
        assert pos.symbol == "AAPL"
        assert pos.side == "LONG"
        assert pos.quantity == 100.0
        assert pos.entry_price == 150.0
        assert pos.mark_price == 155.0
        assert pos.unrealized_pnl == 500.0
        assert pos.leverage == 1
        assert pos.margin_mode == "PORTFOLIO"

    def test_short_position(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__ib__get_positions",
            [
                {
                    "conid": 265598,
                    "symbol": "AAPL",
                    "position": -50,
                    "avgCost": 160.0,
                    "mktPrice": 155.0,
                    "unrealizedPnl": 250.0,
                }
            ],
        )
        provider = IBExchangeProvider(gateway)
        positions = provider.get_positions()

        assert len(positions) == 1
        pos = positions[0]
        assert pos.side == "SHORT"
        assert pos.quantity == 50.0

    def test_zero_position_is_filtered(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__ib__get_positions",
            [
                {
                    "conid": 265598,
                    "symbol": "AAPL",
                    "position": 0,
                    "avgCost": 150.0,
                    "mktPrice": 155.0,
                    "unrealizedPnl": 0.0,
                }
            ],
        )
        provider = IBExchangeProvider(gateway)
        positions = provider.get_positions()

        assert len(positions) == 0

    def test_multiple_positions_mixed(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__ib__get_positions",
            [
                {
                    "conid": 265598,
                    "symbol": "AAPL",
                    "position": 100,
                    "avgCost": 150.0,
                    "mktPrice": 155.0,
                    "unrealizedPnl": 500.0,
                },
                {
                    "conid": 756733,
                    "symbol": "TSLA",
                    "position": -25,
                    "avgCost": 200.0,
                    "mktPrice": 190.0,
                    "unrealizedPnl": 250.0,
                },
            ],
        )
        provider = IBExchangeProvider(gateway)
        positions = provider.get_positions()

        assert len(positions) == 2
        assert positions[0].side == "LONG"
        assert positions[1].side == "SHORT"
        assert positions[1].symbol == "TSLA"

    def test_positions_from_dict_format(self) -> None:
        """IB may return positions wrapped in a dict."""
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__ib__get_positions",
            {
                "positions": [
                    {
                        "conid": 265598,
                        "symbol": "AAPL",
                        "position": 100,
                        "avgCost": 150.0,
                        "mktPrice": 155.0,
                        "unrealizedPnl": 500.0,
                    }
                ]
            },
        )
        provider = IBExchangeProvider(gateway)
        positions = provider.get_positions()

        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"

    def test_positions_error_returns_empty(self) -> None:
        class FailGateway:
            def call_tool(self, tool_name: str, params: dict) -> dict:  # type: ignore[type-arg]
                raise ConnectionError("down")

        provider = IBExchangeProvider(FailGateway())  # type: ignore[arg-type]
        assert provider.get_positions() == []


# ---------------------------------------------------------------------------
# Balance parsing
# ---------------------------------------------------------------------------


class TestIBBalanceParsing:
    def test_parse_ib_balance(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__ib__get_balance",
            {
                "accountId": "U1234",
                "totalCashValue": "100000",
                "netLiquidation": "250000",
                "unrealizedPnL": "5000",
                "availableFunds": "80000",
            },
        )
        provider = IBExchangeProvider(gateway)
        bal = provider.get_balance()

        assert bal is not None
        assert bal.total_balance == 250000.0  # netLiquidation
        assert bal.available_balance == 80000.0
        assert bal.unrealized_pnl == 5000.0
        assert bal.margin_balance == 100000.0  # totalCashValue
        assert bal.asset == "USD"

    def test_balance_with_account_id(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__ib__get_balance",
            {
                "accountId": "U9999",
                "totalCashValue": "50000",
                "netLiquidation": "50000",
                "unrealizedPnL": "0",
                "availableFunds": "50000",
            },
        )
        provider = IBExchangeProvider(gateway, account_id="U9999")
        provider.get_balance()

        params = gateway.call_history[-1].params
        assert params["accountId"] == "U9999"

    def test_balance_error_returns_none(self) -> None:
        class FailGateway:
            def call_tool(self, tool_name: str, params: dict) -> dict:  # type: ignore[type-arg]
                raise ConnectionError("down")

        provider = IBExchangeProvider(FailGateway())  # type: ignore[arg-type]
        assert provider.get_balance() is None


# ---------------------------------------------------------------------------
# Market data: klines
# ---------------------------------------------------------------------------


class TestIBKlines:
    def test_parse_klines(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__ib__get_klines",
            [
                {"t": 1700000000, "o": 150.0, "h": 155.0, "l": 149.0, "c": 154.0, "v": 1000000},
                {"t": 1700003600, "o": 154.0, "h": 157.0, "l": 153.0, "c": 156.0, "v": 800000},
            ],
        )
        provider = IBExchangeProvider(gateway)
        klines = provider.get_klines("AAPL", "1h", 100)

        assert len(klines) == 2
        assert klines[0].open == 150.0
        assert klines[0].close == 154.0
        assert klines[0].volume == 1000000.0
        assert klines[0].symbol == "AAPL"
        assert klines[1].high == 157.0

    def test_klines_error_returns_empty(self) -> None:
        class FailGateway:
            def call_tool(self, tool_name: str, params: dict) -> dict:  # type: ignore[type-arg]
                raise ConnectionError("down")

        provider = IBExchangeProvider(FailGateway())  # type: ignore[arg-type]
        assert provider.get_klines("AAPL") == []

    def test_klines_from_dict_format(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__ib__get_klines",
            {
                "bars": [
                    {"t": 1700000000, "o": 150.0, "h": 155.0, "l": 149.0, "c": 154.0, "v": 500},
                ]
            },
        )
        provider = IBExchangeProvider(gateway)
        klines = provider.get_klines("AAPL")

        assert len(klines) == 1
        assert klines[0].open == 150.0


# ---------------------------------------------------------------------------
# Market data: ticker
# ---------------------------------------------------------------------------


class TestIBTicker:
    def test_parse_ticker(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__ib__get_ticker",
            {
                "symbol": "AAPL",
                "last": 155.0,
                "high": 156.0,
                "low": 153.0,
                "volume": 50000000,
                "change": 1.5,
            },
        )
        provider = IBExchangeProvider(gateway)
        ticker = provider.get_ticker("AAPL")

        assert ticker is not None
        assert ticker.symbol == "AAPL"
        assert ticker.last_price == 155.0
        assert ticker.high_24h == 156.0
        assert ticker.low_24h == 153.0
        assert ticker.volume_24h == 50000000.0

    def test_ticker_error_returns_none(self) -> None:
        class FailGateway:
            def call_tool(self, tool_name: str, params: dict) -> dict:  # type: ignore[type-arg]
                raise ConnectionError("down")

        provider = IBExchangeProvider(FailGateway())  # type: ignore[arg-type]
        assert provider.get_ticker("AAPL") is None


# ---------------------------------------------------------------------------
# Market data: order book
# ---------------------------------------------------------------------------


class TestIBOrderBook:
    def test_parse_order_book(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__ib__get_order_book",
            {
                "bids": [{"price": 154.95, "size": 100}, {"price": 154.90, "size": 200}],
                "asks": [{"price": 155.05, "size": 200}],
            },
        )
        provider = IBExchangeProvider(gateway)
        ob = provider.get_order_book("AAPL")

        assert ob is not None
        assert len(ob.bids) == 2
        assert len(ob.asks) == 1
        assert ob.bids[0].price == 154.95
        assert ob.bids[0].quantity == 100.0  # "size" mapped to "quantity"
        assert ob.asks[0].price == 155.05
        assert ob.asks[0].quantity == 200.0
        assert ob.spread > 0

    def test_order_book_error_returns_none(self) -> None:
        class FailGateway:
            def call_tool(self, tool_name: str, params: dict) -> dict:  # type: ignore[type-arg]
                raise ConnectionError("down")

        provider = IBExchangeProvider(FailGateway())  # type: ignore[arg-type]
        assert provider.get_order_book("AAPL") is None


# ---------------------------------------------------------------------------
# Trade parsing
# ---------------------------------------------------------------------------


class TestIBTrades:
    def test_parse_trades_bot_side(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__ib__get_my_trades",
            [
                {
                    "execId": "E001",
                    "symbol": "AAPL",
                    "side": "BOT",
                    "price": 155.0,
                    "shares": 100,
                    "commission": 1.0,
                    "realizedPNL": 0.0,
                    "time": "20240101-10:00:00",
                }
            ],
        )
        provider = IBExchangeProvider(gateway)
        trades = provider.get_my_trades("AAPL")

        assert len(trades) == 1
        t = trades[0]
        assert t.trade_id == "E001"
        assert t.symbol == "AAPL"
        assert t.side == "BUY"  # BOT -> BUY
        assert t.price == 155.0
        assert t.quantity == 100.0  # shares -> quantity
        assert t.commission == 1.0
        assert t.commission_asset == "USD"
        assert t.realized_pnl == 0.0

    def test_parse_trades_sld_side(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__ib__get_my_trades",
            [
                {
                    "execId": "E002",
                    "symbol": "AAPL",
                    "side": "SLD",
                    "price": 160.0,
                    "shares": 50,
                    "commission": 0.5,
                    "realizedPNL": 250.0,
                    "time": "20240115-14:30:00",
                }
            ],
        )
        provider = IBExchangeProvider(gateway)
        trades = provider.get_my_trades("AAPL")

        assert len(trades) == 1
        assert trades[0].side == "SELL"  # SLD -> SELL
        assert trades[0].realized_pnl == 250.0

    def test_parse_trades_from_dict_format(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__ib__get_my_trades",
            {
                "trades": [
                    {
                        "execId": "E003",
                        "symbol": "SPY",
                        "side": "BOT",
                        "price": 450.0,
                        "shares": 10,
                        "commission": 0.65,
                        "realizedPNL": 0.0,
                        "time": "20240201-09:31:00",
                    }
                ]
            },
        )
        provider = IBExchangeProvider(gateway)
        trades = provider.get_my_trades("SPY")

        assert len(trades) == 1
        assert trades[0].symbol == "SPY"

    def test_trades_error_returns_empty(self) -> None:
        class FailGateway:
            def call_tool(self, tool_name: str, params: dict) -> dict:  # type: ignore[type-arg]
                raise ConnectionError("down")

        provider = IBExchangeProvider(FailGateway())  # type: ignore[arg-type]
        assert provider.get_my_trades("AAPL") == []


# ---------------------------------------------------------------------------
# Order status
# ---------------------------------------------------------------------------


class TestIBOrderStatus:
    def test_get_order_status(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__ib__get_order",
            {"orderId": "12345", "status": "Filled", "symbol": "AAPL"},
        )
        provider = IBExchangeProvider(gateway, account_id="U1234")

        result = provider.get_order_status("AAPL", "12345")
        assert result["status"] == "Filled"
        assert gateway.call_history[-1].tool_name == "mcp__ib__get_order"
        assert gateway.call_history[-1].params["accountId"] == "U1234"


# ---------------------------------------------------------------------------
# IB timestamp parsing
# ---------------------------------------------------------------------------


class TestIBTimestampParsing:
    def test_standard_ib_format(self) -> None:
        ts = IBExchangeProvider._parse_ib_timestamp("20240101-10:00:00")
        assert ts.year == 2024
        assert ts.month == 1
        assert ts.day == 1
        assert ts.hour == 10
        assert ts.minute == 0

    def test_empty_string_fallback(self) -> None:
        ts = IBExchangeProvider._parse_ib_timestamp("")
        assert ts is not None  # falls back to utc_now

    def test_epoch_fallback(self) -> None:
        ts = IBExchangeProvider._parse_ib_timestamp("1700000000")
        assert ts.year == 2023
