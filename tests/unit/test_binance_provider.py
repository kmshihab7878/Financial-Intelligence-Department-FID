"""Tests for the BinanceExchangeProvider."""

from __future__ import annotations

from aiswarm.exchange.provider import AssetClass
from aiswarm.exchange.providers.binance import BinanceConfig, BinanceExchangeProvider
from aiswarm.execution.mcp_gateway import MockMCPGateway


class TestBinanceExchangeProviderProperties:
    def test_exchange_id(self) -> None:
        provider = BinanceExchangeProvider(MockMCPGateway())
        assert provider.exchange_id == "binance"

    def test_supported_asset_classes(self) -> None:
        provider = BinanceExchangeProvider(MockMCPGateway())
        assert AssetClass.SPOT in provider.supported_asset_classes
        assert AssetClass.FUTURES in provider.supported_asset_classes
        assert AssetClass.OPTIONS not in provider.supported_asset_classes


class TestBinanceSymbolNormalization:
    def test_normalize_canonical(self) -> None:
        provider = BinanceExchangeProvider(MockMCPGateway())
        assert provider.normalize_symbol("BTC/USDT") == "BTCUSDT"

    def test_normalize_already_normalized(self) -> None:
        provider = BinanceExchangeProvider(MockMCPGateway())
        assert provider.normalize_symbol("BTCUSDT") == "BTCUSDT"

    def test_to_canonical(self) -> None:
        provider = BinanceExchangeProvider(MockMCPGateway())
        assert provider.to_canonical_symbol("BTCUSDT") == "BTC/USDT"


class TestBinanceMarketData:
    def test_get_klines(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__binance__get_klines",
            [
                {
                    "openTime": 1700000000000,
                    "open": "50000",
                    "high": "51000",
                    "low": "49000",
                    "close": "50500",
                    "volume": "100",
                }
            ],
        )
        provider = BinanceExchangeProvider(gateway)
        klines = provider.get_klines("BTCUSDT", "1h", 100)

        assert len(klines) == 1
        assert klines[0].open == 50000.0
        assert klines[0].close == 50500.0

    def test_get_ticker(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__binance__get_ticker",
            {
                "symbol": "BTCUSDT",
                "lastPrice": "50000",
                "highPrice": "51000",
                "lowPrice": "49000",
                "volume": "1000",
                "priceChangePercent": "2.0",
            },
        )
        provider = BinanceExchangeProvider(gateway)
        ticker = provider.get_ticker("BTCUSDT")

        assert ticker is not None
        assert ticker.last_price == 50000.0
        assert ticker.price_change_pct == 2.0

    def test_get_order_book(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__binance__get_order_book",
            {
                "bids": [["50000", "1.0"], ["49900", "2.0"]],
                "asks": [["50100", "0.5"]],
            },
        )
        provider = BinanceExchangeProvider(gateway)
        ob = provider.get_order_book("BTCUSDT")

        assert ob is not None
        assert len(ob.bids) == 2
        assert len(ob.asks) == 1
        assert ob.spread > 0

    def test_get_funding_rate(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__binance__get_funding_rate",
            {
                "symbol": "BTCUSDT",
                "lastFundingRate": "0.0003",
                "markPrice": "50000",
            },
        )
        provider = BinanceExchangeProvider(gateway)
        fr = provider.get_funding_rate("BTCUSDT")

        assert fr is not None
        assert fr.funding_rate == 0.0003

    def test_get_klines_error_returns_empty(self) -> None:
        class FailGateway:
            def call_tool(self, tool_name: str, params: dict) -> dict:
                raise ConnectionError("down")

        provider = BinanceExchangeProvider(FailGateway())  # type: ignore[arg-type]
        assert provider.get_klines("BTCUSDT") == []


class TestBinanceAccount:
    def test_get_balance(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__binance__get_balance",
            {
                "totalBalance": "100000",
                "availableBalance": "80000",
                "unrealizedProfit": "500",
                "marginBalance": "100500",
            },
        )
        provider = BinanceExchangeProvider(gateway)
        bal = provider.get_balance()

        assert bal is not None
        assert bal.total_balance == 100000.0
        assert bal.available_balance == 80000.0

    def test_get_positions(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__binance__get_positions",
            [
                {
                    "symbol": "BTCUSDT",
                    "positionAmt": "0.5",
                    "entryPrice": "50000",
                    "markPrice": "51000",
                    "unrealizedProfit": "500",
                    "leverage": "3",
                    "marginType": "ISOLATED",
                }
            ],
        )
        provider = BinanceExchangeProvider(gateway)
        positions = provider.get_positions()

        assert len(positions) == 1
        assert positions[0].symbol == "BTC/USDT"
        assert positions[0].quantity == 0.5

    def test_get_income(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__binance__get_income",
            [
                {
                    "incomeType": "REALIZED_PNL",
                    "income": "100.5",
                    "asset": "USDT",
                    "symbol": "BTCUSDT",
                    "time": 1700000000000,
                }
            ],
        )
        provider = BinanceExchangeProvider(gateway)
        income = provider.get_income()

        assert len(income) == 1
        assert income[0].amount == 100.5


class TestBinanceTrading:
    def test_place_futures_order(self) -> None:
        gateway = MockMCPGateway()
        config = BinanceConfig(account_id="acc1")
        provider = BinanceExchangeProvider(gateway, config=config)

        result = provider.place_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=0.1,
            order_type="MARKET",
            venue="futures",
        )

        assert "orderId" in result
        assert gateway.call_history[-1].tool_name == "mcp__binance__create_order"
        assert gateway.call_history[-1].params["symbol"] == "BTCUSDT"

    def test_place_futures_order_with_reduce_only(self) -> None:
        gateway = MockMCPGateway()
        config = BinanceConfig(account_id="acc1")
        provider = BinanceExchangeProvider(gateway, config=config)

        result = provider.place_order(
            symbol="BTCUSDT",
            side="SELL",
            quantity=0.1,
            order_type="MARKET",
            venue="futures",
            reduceOnly=True,
        )

        assert "orderId" in result
        assert gateway.call_history[-1].tool_name == "mcp__binance__create_order"
        assert gateway.call_history[-1].params["reduceOnly"] is True

    def test_place_spot_order(self) -> None:
        gateway = MockMCPGateway()
        config = BinanceConfig(account_id="acc1")
        provider = BinanceExchangeProvider(gateway, config=config)

        result = provider.place_order(
            symbol="BTCUSDT",
            side="SELL",
            quantity=0.5,
            venue="spot",
        )

        assert "orderId" in result
        assert gateway.call_history[-1].tool_name == "mcp__binance__create_spot_order"

    def test_place_spot_order_no_reduce_only(self) -> None:
        """reduceOnly should not be passed for spot orders."""
        gateway = MockMCPGateway()
        config = BinanceConfig(account_id="acc1")
        provider = BinanceExchangeProvider(gateway, config=config)

        provider.place_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=0.1,
            venue="spot",
            reduceOnly=True,
        )

        # reduceOnly should not appear in params for spot orders
        assert "reduceOnly" not in gateway.call_history[-1].params

    def test_cancel_order(self) -> None:
        gateway = MockMCPGateway()
        config = BinanceConfig(account_id="acc1")
        provider = BinanceExchangeProvider(gateway, config=config)

        provider.cancel_order("BTCUSDT", "EX001", venue="futures")
        assert gateway.call_history[-1].tool_name == "mcp__binance__cancel_order"

    def test_cancel_order_spot(self) -> None:
        gateway = MockMCPGateway()
        config = BinanceConfig(account_id="acc1")
        provider = BinanceExchangeProvider(gateway, config=config)

        provider.cancel_order("BTCUSDT", "EX001", venue="spot")
        assert gateway.call_history[-1].tool_name == "mcp__binance__cancel_spot_order"

    def test_cancel_all_orders(self) -> None:
        gateway = MockMCPGateway()
        config = BinanceConfig(account_id="acc1")
        provider = BinanceExchangeProvider(gateway, config=config)

        provider.cancel_all_orders("BTCUSDT", venue="futures")
        assert gateway.call_history[-1].tool_name == "mcp__binance__cancel_all_orders"

        provider.cancel_all_orders("BTCUSDT", venue="spot")
        assert gateway.call_history[-1].tool_name == "mcp__binance__cancel_spot_all_orders"

    def test_get_my_trades(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__binance__get_my_trades",
            [
                {
                    "id": "T001",
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "price": "50000",
                    "qty": "0.1",
                    "commission": "5",
                    "commissionAsset": "USDT",
                    "realizedPnl": "0",
                    "time": 1700000000000,
                    "orderId": "EX001",
                }
            ],
        )
        provider = BinanceExchangeProvider(gateway)
        trades = provider.get_my_trades("BTCUSDT")

        assert len(trades) == 1
        assert trades[0].trade_id == "T001"
        assert trades[0].price == 50000.0

    def test_get_my_trades_spot(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__binance__get_spot_my_trades",
            [
                {
                    "id": "T002",
                    "symbol": "ETHUSDT",
                    "side": "SELL",
                    "price": "3000",
                    "qty": "1.0",
                    "commission": "3",
                    "commissionAsset": "USDT",
                    "realizedPnl": "0",
                    "time": 1700000000000,
                    "orderId": "EX002",
                }
            ],
        )
        provider = BinanceExchangeProvider(gateway)
        trades = provider.get_my_trades("ETHUSDT", venue="spot")

        assert len(trades) == 1
        assert trades[0].trade_id == "T002"


class TestBinanceLeverageMargin:
    def test_set_leverage(self) -> None:
        gateway = MockMCPGateway()
        config = BinanceConfig(account_id="acc1")
        provider = BinanceExchangeProvider(gateway, config=config)

        provider.set_leverage("BTCUSDT", 5)
        assert gateway.call_history[-1].tool_name == "mcp__binance__set_leverage"
        assert gateway.call_history[-1].params["leverage"] == 5

    def test_set_margin_mode(self) -> None:
        gateway = MockMCPGateway()
        config = BinanceConfig(account_id="acc1")
        provider = BinanceExchangeProvider(gateway, config=config)

        provider.set_margin_mode("BTCUSDT", "ISOLATED")
        assert gateway.call_history[-1].tool_name == "mcp__binance__set_margin_mode"
        assert gateway.call_history[-1].params["margin_mode"] == "ISOLATED"


class TestBinanceConfig:
    def test_default_config(self) -> None:
        config = BinanceConfig()
        assert config.account_id == ""
        assert config.rate_limit_calls_per_second == 20.0
        assert config.has_account is False

    def test_config_with_account(self) -> None:
        config = BinanceConfig(account_id="my-binance-account")
        assert config.has_account is True
        assert config.account_id == "my-binance-account"

    def test_config_from_env(self, monkeypatch: object) -> None:
        import os

        old = os.environ.get("BINANCE_ACCOUNT_ID")
        os.environ["BINANCE_ACCOUNT_ID"] = "env-account-123"
        try:
            config = BinanceConfig.from_env()
            assert config.account_id == "env-account-123"
        finally:
            if old is None:
                os.environ.pop("BINANCE_ACCOUNT_ID", None)
            else:
                os.environ["BINANCE_ACCOUNT_ID"] = old
