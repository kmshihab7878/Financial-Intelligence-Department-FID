"""Tests for the ExchangeProvider ABC and AssetClass."""

from __future__ import annotations

import pytest

from aiswarm.exchange.provider import AssetClass, ExchangeProvider


class TestAssetClass:
    def test_flag_combinations(self) -> None:
        combo = AssetClass.SPOT | AssetClass.FUTURES
        assert AssetClass.SPOT in combo
        assert AssetClass.FUTURES in combo
        assert AssetClass.OPTIONS not in combo

    def test_single_flag(self) -> None:
        assert AssetClass.SPOT is not AssetClass.FUTURES

    def test_all_flags(self) -> None:
        all_flags = (
            AssetClass.SPOT
            | AssetClass.FUTURES
            | AssetClass.OPTIONS
            | AssetClass.STOCKS
            | AssetClass.FOREX
        )
        assert AssetClass.SPOT in all_flags
        assert AssetClass.FOREX in all_flags


class TestExchangeProviderABC:
    def test_cannot_instantiate_abc(self) -> None:
        with pytest.raises(TypeError):
            ExchangeProvider()  # type: ignore[abstract]

    def test_default_get_funding_rate_returns_none(self) -> None:
        """Non-abstract methods have sensible defaults."""

        class MinimalProvider(ExchangeProvider):
            @property
            def exchange_id(self) -> str:
                return "test"

            @property
            def supported_asset_classes(self) -> AssetClass:
                return AssetClass.SPOT

            def normalize_symbol(self, canonical: str) -> str:
                return canonical

            def to_canonical_symbol(self, exchange_sym: str) -> str:
                return exchange_sym

            def get_klines(self, symbol, interval="1h", limit=100):  # type: ignore[override]
                return []

            def get_ticker(self, symbol):  # type: ignore[override]
                return None

            def get_order_book(self, symbol):  # type: ignore[override]
                return None

            def get_balance(self):  # type: ignore[override]
                return None

            def get_positions(self):  # type: ignore[override]
                return []

            def place_order(self, symbol, side, quantity, **kw):  # type: ignore[override]
                return {"orderId": "test"}

            def cancel_order(self, symbol, order_id, venue="futures"):  # type: ignore[override]
                return {}

            def cancel_all_orders(self, symbol, venue="futures"):  # type: ignore[override]
                return {}

        p = MinimalProvider()
        assert p.get_funding_rate("BTC") is None
        assert p.get_income() == []
        assert p.get_my_trades("BTC") == []

    def test_default_set_leverage_raises(self) -> None:
        class MinimalProvider(ExchangeProvider):
            @property
            def exchange_id(self) -> str:
                return "test"

            @property
            def supported_asset_classes(self) -> AssetClass:
                return AssetClass.SPOT

            def normalize_symbol(self, canonical: str) -> str:
                return canonical

            def to_canonical_symbol(self, exchange_sym: str) -> str:
                return exchange_sym

            def get_klines(self, symbol, interval="1h", limit=100):  # type: ignore[override]
                return []

            def get_ticker(self, symbol):  # type: ignore[override]
                return None

            def get_order_book(self, symbol):  # type: ignore[override]
                return None

            def get_balance(self):  # type: ignore[override]
                return None

            def get_positions(self):  # type: ignore[override]
                return []

            def place_order(self, symbol, side, quantity, **kw):  # type: ignore[override]
                return {"orderId": "test"}

            def cancel_order(self, symbol, order_id, venue="futures"):  # type: ignore[override]
                return {}

            def cancel_all_orders(self, symbol, venue="futures"):  # type: ignore[override]
                return {}

        p = MinimalProvider()
        with pytest.raises(NotImplementedError):
            p.set_leverage("BTC", 5)
        with pytest.raises(NotImplementedError):
            p.set_margin_mode("BTC", "ISOLATED")
