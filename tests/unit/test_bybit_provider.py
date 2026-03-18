"""Tests for the BybitExchangeProvider.

Every test sets Bybit v5-shaped responses on MockMCPGateway (with the
``retCode`` / ``result`` envelope) so we validate the full unwrap-and-parse
pipeline.
"""

from __future__ import annotations

import pytest

from aiswarm.exchange.provider import AssetClass
from aiswarm.exchange.providers.bybit import (
    BybitExchangeProvider,
    _bybit_side_to_canonical,
    _bybit_trade_mode_to_canonical,
    _margin_mode_to_bybit,
    _normalize_symbol,
    _to_canonical_symbol,
    _venue_to_category,
)
from aiswarm.execution.mcp_gateway import MockMCPGateway


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def gateway() -> MockMCPGateway:
    return MockMCPGateway()


@pytest.fixture()
def provider(gateway: MockMCPGateway) -> BybitExchangeProvider:
    return BybitExchangeProvider(gateway)


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestBybitProperties:
    def test_exchange_id(self, provider: BybitExchangeProvider) -> None:
        assert provider.exchange_id == "bybit"

    def test_supported_asset_classes(self, provider: BybitExchangeProvider) -> None:
        assert AssetClass.SPOT in provider.supported_asset_classes
        assert AssetClass.FUTURES in provider.supported_asset_classes
        assert AssetClass.OPTIONS in provider.supported_asset_classes
        assert AssetClass.STOCKS not in provider.supported_asset_classes
        assert AssetClass.FOREX not in provider.supported_asset_classes


# ---------------------------------------------------------------------------
# Symbol normalization
# ---------------------------------------------------------------------------


class TestBybitSymbolNormalization:
    def test_normalize_canonical_btcusdt(self, provider: BybitExchangeProvider) -> None:
        assert provider.normalize_symbol("BTC/USDT") == "BTCUSDT"

    def test_normalize_canonical_ethusdc(self, provider: BybitExchangeProvider) -> None:
        assert provider.normalize_symbol("ETH/USDC") == "ETHUSDC"

    def test_normalize_already_normalized(self, provider: BybitExchangeProvider) -> None:
        assert provider.normalize_symbol("BTCUSDT") == "BTCUSDT"

    def test_to_canonical_linear(self, provider: BybitExchangeProvider) -> None:
        assert provider.to_canonical_symbol("BTCUSDT") == "BTC/USDT"

    def test_to_canonical_usdc(self, provider: BybitExchangeProvider) -> None:
        assert provider.to_canonical_symbol("ETHUSDC") == "ETH/USDC"

    def test_to_canonical_inverse(self, provider: BybitExchangeProvider) -> None:
        # Inverse symbol "BTCUSD" -> "BTC/USD"
        assert provider.to_canonical_symbol("BTCUSD") == "BTC/USD"

    def test_to_canonical_already_canonical(self, provider: BybitExchangeProvider) -> None:
        assert provider.to_canonical_symbol("BTC/USDT") == "BTC/USDT"


class TestSymbolHelperFunctions:
    """Direct tests on module-level symbol helpers."""

    def test_normalize_symbol(self) -> None:
        assert _normalize_symbol("BTC/USDT") == "BTCUSDT"
        assert _normalize_symbol("SOL/USDC") == "SOLUSDC"
        assert _normalize_symbol("BTCUSDT") == "BTCUSDT"

    def test_to_canonical_symbol_known_quotes(self) -> None:
        assert _to_canonical_symbol("BTCUSDT") == "BTC/USDT"
        assert _to_canonical_symbol("ETHBUSD") == "ETH/BUSD"
        assert _to_canonical_symbol("SOLUSDC") == "SOL/USDC"
        assert _to_canonical_symbol("BTCUSD") == "BTC/USD"

    def test_to_canonical_symbol_passthrough(self) -> None:
        # Unknown suffix -> returned as-is.
        assert _to_canonical_symbol("XYZABC") == "XYZABC"


# ---------------------------------------------------------------------------
# Venue / category mapping
# ---------------------------------------------------------------------------


class TestVenueToCategory:
    def test_futures_to_linear(self) -> None:
        assert _venue_to_category("futures") == "linear"

    def test_spot_to_spot(self) -> None:
        assert _venue_to_category("spot") == "spot"

    def test_passthrough_inverse(self) -> None:
        assert _venue_to_category("inverse") == "inverse"

    def test_passthrough_option(self) -> None:
        assert _venue_to_category("option") == "option"


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


class TestMappingHelpers:
    def test_bybit_side_buy(self) -> None:
        assert _bybit_side_to_canonical("Buy") == "LONG"

    def test_bybit_side_sell(self) -> None:
        assert _bybit_side_to_canonical("Sell") == "SHORT"

    def test_bybit_side_lowercase(self) -> None:
        assert _bybit_side_to_canonical("buy") == "LONG"
        assert _bybit_side_to_canonical("sell") == "SHORT"

    def test_bybit_side_unknown(self) -> None:
        assert _bybit_side_to_canonical("None") == "NONE"

    def test_trade_mode_isolated(self) -> None:
        assert _bybit_trade_mode_to_canonical("1") == "ISOLATED"
        assert _bybit_trade_mode_to_canonical("ISOLATED") == "ISOLATED"

    def test_trade_mode_cross(self) -> None:
        assert _bybit_trade_mode_to_canonical("0") == "CROSSED"
        assert _bybit_trade_mode_to_canonical("CROSSED") == "CROSSED"

    def test_margin_mode_to_bybit(self) -> None:
        assert _margin_mode_to_bybit("ISOLATED") == "1"
        assert _margin_mode_to_bybit("isolated") == "1"
        assert _margin_mode_to_bybit("CROSSED") == "0"
        assert _margin_mode_to_bybit("cross") == "0"


# ---------------------------------------------------------------------------
# Market Data — Klines
# ---------------------------------------------------------------------------


class TestBybitKlines:
    def test_get_klines_parses_v5_response(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_klines",
            {
                "retCode": 0,
                "result": {
                    "list": [
                        ["1700000000000", "50000", "51000", "49000", "50500", "100", "5000000"],
                        ["1700003600000", "50500", "52000", "50000", "51500", "200", "10000000"],
                    ]
                },
            },
        )

        klines = provider.get_klines("BTCUSDT", "1h", 100)

        assert len(klines) == 2
        assert klines[0].open == 50000.0
        assert klines[0].high == 51000.0
        assert klines[0].low == 49000.0
        assert klines[0].close == 50500.0
        assert klines[0].volume == 100.0
        assert klines[0].symbol == "BTC/USDT"
        assert klines[1].close == 51500.0

    def test_get_klines_sends_category(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_klines",
            {"retCode": 0, "result": {"list": []}},
        )
        provider.get_klines("BTCUSDT")
        assert gateway.call_history[-1].params["category"] == "linear"

    def test_get_klines_error_returns_empty(self) -> None:
        class FailGateway:
            def call_tool(self, tool_name: str, params: dict) -> dict:  # type: ignore[type-arg]
                raise ConnectionError("exchange down")

        provider = BybitExchangeProvider(FailGateway())  # type: ignore[arg-type]
        assert provider.get_klines("BTCUSDT") == []

    def test_get_klines_nonzero_retcode_returns_empty(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_klines",
            {"retCode": 10001, "retMsg": "Invalid symbol", "result": {}},
        )
        assert provider.get_klines("INVALID") == []

    def test_get_klines_short_rows_skipped(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_klines",
            {
                "retCode": 0,
                "result": {
                    "list": [
                        ["1700000000000", "50000"],  # too short
                        ["1700000000000", "50000", "51000", "49000", "50500", "100", "5000000"],
                    ]
                },
            },
        )
        klines = provider.get_klines("BTCUSDT")
        assert len(klines) == 1


# ---------------------------------------------------------------------------
# Market Data — Ticker
# ---------------------------------------------------------------------------


class TestBybitTicker:
    def test_get_ticker_parses_v5_response(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_ticker",
            {
                "retCode": 0,
                "result": {
                    "list": [
                        {
                            "symbol": "BTCUSDT",
                            "lastPrice": "50000.50",
                            "highPrice24h": "51000",
                            "lowPrice24h": "49000",
                            "volume24h": "12345.67",
                            "price24hPcnt": "0.0250",
                        }
                    ]
                },
            },
        )

        ticker = provider.get_ticker("BTCUSDT")

        assert ticker is not None
        assert ticker.symbol == "BTC/USDT"
        assert ticker.last_price == 50000.50
        assert ticker.high_24h == 51000.0
        assert ticker.low_24h == 49000.0
        assert ticker.volume_24h == 12345.67
        assert ticker.price_change_pct == 0.025

    def test_get_ticker_empty_list_returns_none(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_ticker",
            {"retCode": 0, "result": {"list": []}},
        )
        assert provider.get_ticker("BTCUSDT") is None


# ---------------------------------------------------------------------------
# Market Data — Order Book
# ---------------------------------------------------------------------------


class TestBybitOrderBook:
    def test_get_order_book_parses_v5_response(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_order_book",
            {
                "retCode": 0,
                "result": {
                    "b": [["50000", "1.5"], ["49900", "2.0"]],
                    "a": [["50100", "0.8"], ["50200", "1.2"]],
                },
            },
        )

        ob = provider.get_order_book("BTCUSDT")

        assert ob is not None
        assert ob.symbol == "BTC/USDT"
        assert len(ob.bids) == 2
        assert len(ob.asks) == 2
        assert ob.bids[0].price == 50000.0
        assert ob.bids[0].quantity == 1.5
        assert ob.asks[0].price == 50100.0
        assert ob.spread == pytest.approx(100.0)

    def test_get_order_book_empty_book(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_order_book",
            {"retCode": 0, "result": {"b": [], "a": []}},
        )
        ob = provider.get_order_book("BTCUSDT")
        assert ob is not None
        assert len(ob.bids) == 0
        assert len(ob.asks) == 0
        assert ob.spread == 0.0


# ---------------------------------------------------------------------------
# Market Data — Funding Rate
# ---------------------------------------------------------------------------


class TestBybitFundingRate:
    def test_get_funding_rate_parses_v5_response(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_funding_rate",
            {
                "retCode": 0,
                "result": {
                    "list": [
                        {
                            "symbol": "BTCUSDT",
                            "fundingRate": "0.0003",
                            "markPrice": "50000",
                            "nextFundingTime": "1700000000000",
                        }
                    ]
                },
            },
        )

        fr = provider.get_funding_rate("BTCUSDT")

        assert fr is not None
        assert fr.symbol == "BTC/USDT"
        assert fr.funding_rate == 0.0003
        assert fr.mark_price == 50000.0
        assert fr.next_funding_time is not None

    def test_get_funding_rate_empty_returns_none(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_funding_rate",
            {"retCode": 0, "result": {"list": []}},
        )
        assert provider.get_funding_rate("BTCUSDT") is None


# ---------------------------------------------------------------------------
# Account — Balance
# ---------------------------------------------------------------------------


class TestBybitBalance:
    def test_get_balance_parses_v5_response(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_balance",
            {
                "retCode": 0,
                "result": {
                    "list": [
                        {
                            "totalEquity": "100000.50",
                            "availableBalance": "80000.25",
                            "totalPerpUPL": "500.10",
                            "totalMarginBalance": "100500.60",
                        }
                    ]
                },
            },
        )

        bal = provider.get_balance()

        assert bal is not None
        assert bal.total_balance == 100000.50
        assert bal.available_balance == 80000.25
        assert bal.unrealized_pnl == 500.10
        assert bal.margin_balance == 100500.60
        assert bal.asset == "USDT"

    def test_get_balance_empty_list_returns_none(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_balance",
            {"retCode": 0, "result": {"list": []}},
        )
        assert provider.get_balance() is None

    def test_get_balance_sends_account_type(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_balance",
            {"retCode": 0, "result": {"list": []}},
        )
        provider.get_balance()
        assert gateway.call_history[-1].params["accountType"] == "UNIFIED"


# ---------------------------------------------------------------------------
# Account — Positions
# ---------------------------------------------------------------------------


class TestBybitPositions:
    def test_get_positions_parses_v5_response(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_positions",
            {
                "retCode": 0,
                "result": {
                    "list": [
                        {
                            "symbol": "BTCUSDT",
                            "side": "Buy",
                            "size": "0.5",
                            "avgPrice": "50000",
                            "markPrice": "51000",
                            "unrealisedPnl": "500",
                            "leverage": "3",
                            "tradeMode": "1",
                        },
                        {
                            "symbol": "ETHUSDT",
                            "side": "Sell",
                            "size": "10",
                            "avgPrice": "3000",
                            "markPrice": "2950",
                            "unrealisedPnl": "500",
                            "leverage": "5",
                            "tradeMode": "0",
                        },
                    ]
                },
            },
        )

        positions = provider.get_positions()

        assert len(positions) == 2

        btc_pos = positions[0]
        assert btc_pos.symbol == "BTC/USDT"
        assert btc_pos.side == "LONG"
        assert btc_pos.quantity == 0.5
        assert btc_pos.entry_price == 50000.0
        assert btc_pos.mark_price == 51000.0
        assert btc_pos.unrealized_pnl == 500.0
        assert btc_pos.leverage == 3
        assert btc_pos.margin_mode == "ISOLATED"

        eth_pos = positions[1]
        assert eth_pos.symbol == "ETH/USDT"
        assert eth_pos.side == "SHORT"
        assert eth_pos.leverage == 5
        assert eth_pos.margin_mode == "CROSSED"

    def test_get_positions_empty(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_positions",
            {"retCode": 0, "result": {"list": []}},
        )
        assert provider.get_positions() == []


# ---------------------------------------------------------------------------
# Account — Income
# ---------------------------------------------------------------------------


class TestBybitIncome:
    def test_get_income_parses_v5_response(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_income",
            {
                "retCode": 0,
                "result": {
                    "list": [
                        {
                            "incomeType": "REALIZED_PNL",
                            "amount": "150.50",
                            "asset": "USDT",
                            "symbol": "BTCUSDT",
                            "updatedTime": "1700000000000",
                        }
                    ]
                },
            },
        )

        income = provider.get_income()

        assert len(income) == 1
        assert income[0].income_type == "REALIZED_PNL"
        assert income[0].amount == 150.50
        assert income[0].asset == "USDT"
        assert income[0].symbol == "BTC/USDT"

    def test_get_income_empty(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_income",
            {"retCode": 0, "result": {"list": []}},
        )
        assert provider.get_income() == []


# ---------------------------------------------------------------------------
# Trading — Place Order
# ---------------------------------------------------------------------------


class TestBybitPlaceOrder:
    def test_place_futures_order(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__create_order",
            {
                "retCode": 0,
                "result": {
                    "orderId": "ORD001",
                    "orderLinkId": "link1",
                    "symbol": "BTCUSDT",
                },
            },
        )

        result = provider.place_order(
            symbol="BTC/USDT",
            side="Buy",
            quantity=0.1,
            order_type="Market",
            venue="futures",
        )

        assert result["orderId"] == "ORD001"
        call = gateway.call_history[-1]
        assert call.tool_name == "mcp__bybit__create_order"
        assert call.params["category"] == "linear"
        assert call.params["symbol"] == "BTCUSDT"
        assert call.params["side"] == "Buy"
        assert call.params["qty"] == "0.1"
        assert call.params["orderType"] == "Market"

    def test_place_spot_order(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__create_order",
            {
                "retCode": 0,
                "result": {
                    "orderId": "ORD002",
                    "orderLinkId": "",
                    "symbol": "ETHUSDT",
                },
            },
        )

        result = provider.place_order(
            symbol="ETH/USDT",
            side="Sell",
            quantity=1.0,
            venue="spot",
        )

        assert result["orderId"] == "ORD002"
        call = gateway.call_history[-1]
        assert call.params["category"] == "spot"

    def test_place_limit_order_includes_price_and_tif(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__create_order",
            {
                "retCode": 0,
                "result": {"orderId": "ORD003", "symbol": "BTCUSDT"},
            },
        )

        provider.place_order(
            symbol="BTCUSDT",
            side="Buy",
            quantity=0.5,
            order_type="Limit",
            price=48000.0,
            venue="futures",
        )

        call = gateway.call_history[-1]
        assert call.params["price"] == "48000.0"
        assert call.params["timeInForce"] == "GTC"

    def test_place_order_normalizes_orderID_key(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        """Ensure ``orderID`` (capital D) gets normalised to ``orderId``."""
        gateway.set_response(
            "mcp__bybit__create_order",
            {
                "retCode": 0,
                "result": {"orderID": "ORD004", "symbol": "BTCUSDT"},
            },
        )

        result = provider.place_order(symbol="BTCUSDT", side="Buy", quantity=0.1)
        assert result["orderId"] == "ORD004"


# ---------------------------------------------------------------------------
# Trading — Cancel Order
# ---------------------------------------------------------------------------


class TestBybitCancelOrder:
    def test_cancel_futures_order(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__cancel_order",
            {
                "retCode": 0,
                "result": {"orderId": "ORD001"},
            },
        )

        result = provider.cancel_order("BTCUSDT", "ORD001", venue="futures")

        assert result["orderId"] == "ORD001"
        call = gateway.call_history[-1]
        assert call.tool_name == "mcp__bybit__cancel_order"
        assert call.params["category"] == "linear"
        assert call.params["orderId"] == "ORD001"

    def test_cancel_spot_order(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__cancel_order",
            {"retCode": 0, "result": {"orderId": "ORD005"}},
        )
        provider.cancel_order("ETHUSDT", "ORD005", venue="spot")
        assert gateway.call_history[-1].params["category"] == "spot"


# ---------------------------------------------------------------------------
# Trading — Cancel All Orders
# ---------------------------------------------------------------------------


class TestBybitCancelAllOrders:
    def test_cancel_all_futures(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__cancel_all_orders",
            {"retCode": 0, "result": {"success": True}},
        )
        result = provider.cancel_all_orders("BTCUSDT", venue="futures")
        call = gateway.call_history[-1]
        assert call.tool_name == "mcp__bybit__cancel_all_orders"
        assert call.params["category"] == "linear"
        assert "success" in result

    def test_cancel_all_spot(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__cancel_all_orders",
            {"retCode": 0, "result": {"success": True}},
        )
        provider.cancel_all_orders("ETHUSDT", venue="spot")
        assert gateway.call_history[-1].params["category"] == "spot"


# ---------------------------------------------------------------------------
# Trading — Order Status
# ---------------------------------------------------------------------------


class TestBybitOrderStatus:
    def test_get_order_status(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_order",
            {
                "retCode": 0,
                "result": {
                    "orderId": "ORD001",
                    "orderStatus": "Filled",
                    "symbol": "BTCUSDT",
                },
            },
        )

        result = provider.get_order_status("BTCUSDT", "ORD001")

        assert result["orderId"] == "ORD001"
        assert result["orderStatus"] == "Filled"
        call = gateway.call_history[-1]
        assert call.tool_name == "mcp__bybit__get_order"
        assert call.params["category"] == "linear"


# ---------------------------------------------------------------------------
# Trading — My Trades
# ---------------------------------------------------------------------------


class TestBybitMyTrades:
    def test_get_my_trades_parses_v5_response(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_my_trades",
            {
                "retCode": 0,
                "result": {
                    "list": [
                        {
                            "execId": "T001",
                            "symbol": "BTCUSDT",
                            "side": "Buy",
                            "execPrice": "50000",
                            "execQty": "0.1",
                            "execFee": "5.0",
                            "feeCurrency": "USDT",
                            "closedPnl": "0",
                            "execTime": "1700000000000",
                            "orderId": "ORD001",
                        },
                        {
                            "execId": "T002",
                            "symbol": "BTCUSDT",
                            "side": "Sell",
                            "execPrice": "51000",
                            "execQty": "0.1",
                            "execFee": "5.1",
                            "feeCurrency": "USDT",
                            "closedPnl": "100",
                            "execTime": "1700003600000",
                            "orderId": "ORD002",
                        },
                    ]
                },
            },
        )

        trades = provider.get_my_trades("BTCUSDT")

        assert len(trades) == 2

        t1 = trades[0]
        assert t1.trade_id == "T001"
        assert t1.symbol == "BTC/USDT"
        assert t1.side == "BUY"
        assert t1.price == 50000.0
        assert t1.quantity == 0.1
        assert t1.commission == 5.0
        assert t1.commission_asset == "USDT"
        assert t1.realized_pnl == 0.0
        assert t1.order_id == "ORD001"

        t2 = trades[1]
        assert t2.side == "SELL"
        assert t2.realized_pnl == 100.0

    def test_get_my_trades_spot_venue(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_my_trades",
            {"retCode": 0, "result": {"list": []}},
        )
        provider.get_my_trades("BTCUSDT", venue="spot")
        assert gateway.call_history[-1].params["category"] == "spot"

    def test_get_my_trades_error_returns_empty(self) -> None:
        class FailGateway:
            def call_tool(self, tool_name: str, params: dict) -> dict:  # type: ignore[type-arg]
                raise ConnectionError("down")

        provider = BybitExchangeProvider(FailGateway())  # type: ignore[arg-type]
        assert provider.get_my_trades("BTCUSDT") == []


# ---------------------------------------------------------------------------
# Leverage / Margin
# ---------------------------------------------------------------------------


class TestBybitLeverageMargin:
    def test_set_leverage(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__set_leverage",
            {"retCode": 0, "result": {}},
        )

        provider.set_leverage("BTCUSDT", 10)

        call = gateway.call_history[-1]
        assert call.tool_name == "mcp__bybit__set_leverage"
        assert call.params["buyLeverage"] == "10"
        assert call.params["sellLeverage"] == "10"
        assert call.params["category"] == "linear"

    def test_set_margin_mode_isolated(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__set_margin_mode",
            {"retCode": 0, "result": {}},
        )

        provider.set_margin_mode("BTCUSDT", "ISOLATED")

        call = gateway.call_history[-1]
        assert call.tool_name == "mcp__bybit__set_margin_mode"
        assert call.params["tradeMode"] == "1"
        assert call.params["category"] == "linear"

    def test_set_margin_mode_cross(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__set_margin_mode",
            {"retCode": 0, "result": {}},
        )

        provider.set_margin_mode("BTCUSDT", "CROSSED")

        call = gateway.call_history[-1]
        assert call.params["tradeMode"] == "0"


# ---------------------------------------------------------------------------
# Edge cases — v5 envelope handling
# ---------------------------------------------------------------------------


class TestBybitV5EnvelopeHandling:
    def test_nonzero_retcode_returns_safe_default(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        """Non-zero retCode should be treated as an error for safe methods."""
        gateway.set_response(
            "mcp__bybit__get_ticker",
            {"retCode": 10001, "retMsg": "params error", "result": {}},
        )
        assert provider.get_ticker("BTCUSDT") is None

    def test_nonzero_retcode_positions_returns_empty(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_positions",
            {"retCode": 33004, "retMsg": "unauthorized", "result": {}},
        )
        assert provider.get_positions() == []

    def test_missing_result_key_still_works(
        self,
        gateway: MockMCPGateway,
        provider: BybitExchangeProvider,
    ) -> None:
        """If the response has no ``retCode`` (e.g. mock), use it as-is."""
        gateway.set_response(
            "mcp__bybit__get_klines",
            {
                "list": [
                    ["1700000000000", "50000", "51000", "49000", "50500", "100", "5000000"],
                ]
            },
        )
        klines = provider.get_klines("BTCUSDT")
        assert len(klines) == 1
        assert klines[0].open == 50000.0


# ---------------------------------------------------------------------------
# Integration: tool name routing
# ---------------------------------------------------------------------------


class TestBybitToolNameRouting:
    """Verify that the correct MCP tool names are invoked for each operation."""

    def test_klines_tool(self, gateway: MockMCPGateway, provider: BybitExchangeProvider) -> None:
        gateway.set_response("mcp__bybit__get_klines", {"retCode": 0, "result": {"list": []}})
        provider.get_klines("BTCUSDT")
        assert gateway.call_history[-1].tool_name == "mcp__bybit__get_klines"

    def test_ticker_tool(self, gateway: MockMCPGateway, provider: BybitExchangeProvider) -> None:
        gateway.set_response("mcp__bybit__get_ticker", {"retCode": 0, "result": {"list": []}})
        provider.get_ticker("BTCUSDT")
        assert gateway.call_history[-1].tool_name == "mcp__bybit__get_ticker"

    def test_order_book_tool(
        self, gateway: MockMCPGateway, provider: BybitExchangeProvider
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_order_book",
            {"retCode": 0, "result": {"b": [], "a": []}},
        )
        provider.get_order_book("BTCUSDT")
        assert gateway.call_history[-1].tool_name == "mcp__bybit__get_order_book"

    def test_funding_rate_tool(
        self, gateway: MockMCPGateway, provider: BybitExchangeProvider
    ) -> None:
        gateway.set_response(
            "mcp__bybit__get_funding_rate",
            {"retCode": 0, "result": {"list": []}},
        )
        provider.get_funding_rate("BTCUSDT")
        assert gateway.call_history[-1].tool_name == "mcp__bybit__get_funding_rate"

    def test_balance_tool(self, gateway: MockMCPGateway, provider: BybitExchangeProvider) -> None:
        gateway.set_response("mcp__bybit__get_balance", {"retCode": 0, "result": {"list": []}})
        provider.get_balance()
        assert gateway.call_history[-1].tool_name == "mcp__bybit__get_balance"

    def test_positions_tool(self, gateway: MockMCPGateway, provider: BybitExchangeProvider) -> None:
        gateway.set_response(
            "mcp__bybit__get_positions",
            {"retCode": 0, "result": {"list": []}},
        )
        provider.get_positions()
        assert gateway.call_history[-1].tool_name == "mcp__bybit__get_positions"

    def test_income_tool(self, gateway: MockMCPGateway, provider: BybitExchangeProvider) -> None:
        gateway.set_response("mcp__bybit__get_income", {"retCode": 0, "result": {"list": []}})
        provider.get_income()
        assert gateway.call_history[-1].tool_name == "mcp__bybit__get_income"

    def test_create_order_tool(
        self, gateway: MockMCPGateway, provider: BybitExchangeProvider
    ) -> None:
        gateway.set_response(
            "mcp__bybit__create_order",
            {"retCode": 0, "result": {"orderId": "X"}},
        )
        provider.place_order("BTCUSDT", "Buy", 0.1)
        assert gateway.call_history[-1].tool_name == "mcp__bybit__create_order"

    def test_cancel_order_tool(
        self, gateway: MockMCPGateway, provider: BybitExchangeProvider
    ) -> None:
        gateway.set_response(
            "mcp__bybit__cancel_order",
            {"retCode": 0, "result": {"orderId": "X"}},
        )
        provider.cancel_order("BTCUSDT", "X")
        assert gateway.call_history[-1].tool_name == "mcp__bybit__cancel_order"

    def test_cancel_all_orders_tool(
        self, gateway: MockMCPGateway, provider: BybitExchangeProvider
    ) -> None:
        gateway.set_response(
            "mcp__bybit__cancel_all_orders",
            {"retCode": 0, "result": {}},
        )
        provider.cancel_all_orders("BTCUSDT")
        assert gateway.call_history[-1].tool_name == "mcp__bybit__cancel_all_orders"

    def test_get_order_tool(self, gateway: MockMCPGateway, provider: BybitExchangeProvider) -> None:
        gateway.set_response(
            "mcp__bybit__get_order",
            {"retCode": 0, "result": {"orderId": "X"}},
        )
        provider.get_order_status("BTCUSDT", "X")
        assert gateway.call_history[-1].tool_name == "mcp__bybit__get_order"

    def test_my_trades_tool(self, gateway: MockMCPGateway, provider: BybitExchangeProvider) -> None:
        gateway.set_response(
            "mcp__bybit__get_my_trades",
            {"retCode": 0, "result": {"list": []}},
        )
        provider.get_my_trades("BTCUSDT")
        assert gateway.call_history[-1].tool_name == "mcp__bybit__get_my_trades"

    def test_set_leverage_tool(
        self, gateway: MockMCPGateway, provider: BybitExchangeProvider
    ) -> None:
        gateway.set_response("mcp__bybit__set_leverage", {"retCode": 0, "result": {}})
        provider.set_leverage("BTCUSDT", 5)
        assert gateway.call_history[-1].tool_name == "mcp__bybit__set_leverage"

    def test_set_margin_mode_tool(
        self, gateway: MockMCPGateway, provider: BybitExchangeProvider
    ) -> None:
        gateway.set_response("mcp__bybit__set_margin_mode", {"retCode": 0, "result": {}})
        provider.set_margin_mode("BTCUSDT", "ISOLATED")
        assert gateway.call_history[-1].tool_name == "mcp__bybit__set_margin_mode"
