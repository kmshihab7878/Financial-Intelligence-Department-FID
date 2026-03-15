"""Tests for the Aster DEX data provider and canonical types."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aiswarm.data.providers.aster import (
    AsterDataProvider,
    OrderBook,
    OrderBookLevel,
    parse_balance,
    parse_funding_rate,
    parse_ohlcv,
    parse_position,
    parse_ticker,
)
from aiswarm.data.providers.aster_config import normalize_symbol, to_canonical_symbol


class TestSymbolNormalization:
    def test_slash_format(self) -> None:
        assert normalize_symbol("BTC/USDT") == "BTCUSDT"

    def test_already_normalized(self) -> None:
        assert normalize_symbol("BTCUSDT") == "BTCUSDT"

    def test_to_canonical(self) -> None:
        assert to_canonical_symbol("BTCUSDT") == "BTC/USDT"
        assert to_canonical_symbol("ETHUSDT") == "ETH/USDT"

    def test_unknown_symbol(self) -> None:
        assert normalize_symbol("XYZABC") == "XYZABC"


class TestParseOHLCV:
    def test_basic_parse(self) -> None:
        raw = {
            "openTime": 1700000000000,
            "open": "50000.0",
            "high": "51000.0",
            "low": "49000.0",
            "close": "50500.0",
            "volume": "1000.0",
        }
        candle = parse_ohlcv(raw, "BTCUSDT")
        assert candle.close == 50500.0
        assert candle.symbol == "BTC/USDT"
        assert candle.timestamp.year >= 2023

    def test_alternative_keys(self) -> None:
        raw = {"t": 1700000000, "o": "100", "h": "110", "l": "90", "c": "105", "v": "500"}
        candle = parse_ohlcv(raw, "ETHUSDT")
        assert candle.close == 105.0


class TestParseTicker:
    def test_basic_parse(self) -> None:
        raw = {
            "symbol": "BTCUSDT",
            "lastPrice": "50000",
            "highPrice": "51000",
            "lowPrice": "49000",
            "volume": "10000",
            "priceChangePercent": "2.5",
        }
        ticker = parse_ticker(raw)
        assert ticker.last_price == 50000.0
        assert ticker.symbol == "BTC/USDT"
        assert ticker.price_change_pct == 2.5


class TestParseFundingRate:
    def test_basic_parse(self) -> None:
        raw = {
            "symbol": "BTCUSDT",
            "lastFundingRate": "0.0003",
            "markPrice": "50000",
            "nextFundingTime": 1700000000000,
        }
        fr = parse_funding_rate(raw)
        assert fr.funding_rate == 0.0003
        assert fr.mark_price == 50000.0
        assert fr.next_funding_time is not None


class TestParseBalance:
    def test_basic_parse(self) -> None:
        raw = {
            "totalBalance": "10000",
            "availableBalance": "8000",
            "unrealizedProfit": "500",
            "marginBalance": "9500",
        }
        balance = parse_balance(raw)
        assert balance.total_balance == 10000.0
        assert balance.available_balance == 8000.0


class TestParsePosition:
    def test_long_position(self) -> None:
        raw = {
            "symbol": "BTCUSDT",
            "positionAmt": "0.5",
            "entryPrice": "50000",
            "markPrice": "51000",
            "unrealizedProfit": "500",
            "leverage": "10",
            "marginType": "isolated",
        }
        pos = parse_position(raw)
        assert pos.side == "LONG"
        assert pos.quantity == 0.5
        assert pos.leverage == 10

    def test_short_position(self) -> None:
        raw = {
            "symbol": "ETHUSDT",
            "positionAmt": "-2.0",
            "entryPrice": "3000",
            "markPrice": "2900",
            "unrealizedProfit": "200",
            "leverage": "5",
            "marginType": "crossed",
        }
        pos = parse_position(raw)
        assert pos.side == "SHORT"
        assert pos.quantity == 2.0


class TestOrderBook:
    def test_spread(self) -> None:
        ob = OrderBook(
            symbol="BTC/USDT",
            bids=(OrderBookLevel(price=50000, quantity=1),),
            asks=(OrderBookLevel(price=50010, quantity=1),),
            timestamp=datetime.now(timezone.utc),
        )
        assert ob.spread == 10.0
        assert ob.spread_bps == pytest.approx(2.0, rel=0.01)

    def test_depth(self) -> None:
        ob = OrderBook(
            symbol="BTC/USDT",
            bids=(
                OrderBookLevel(price=50000, quantity=10),
                OrderBookLevel(price=49990, quantity=5),
            ),
            asks=(
                OrderBookLevel(price=50010, quantity=8),
                OrderBookLevel(price=50020, quantity=3),
            ),
            timestamp=datetime.now(timezone.utc),
        )
        assert ob.bid_depth == 50000 * 10 + 49990 * 5
        assert ob.ask_depth == 50010 * 8 + 50020 * 3


class TestAsterDataProvider:
    def test_parse_klines_list(self) -> None:
        provider = AsterDataProvider()
        raw = [
            {
                "openTime": 1700000000000,
                "open": "100",
                "high": "110",
                "low": "90",
                "close": "105",
                "volume": "1000",
            },
            {
                "openTime": 1700003600000,
                "open": "105",
                "high": "115",
                "low": "95",
                "close": "110",
                "volume": "800",
            },
        ]
        candles = provider.parse_klines(raw, "BTCUSDT")
        assert len(candles) == 2
        assert candles[1].close == 110.0

    def test_compute_liquidity_score(self) -> None:
        provider = AsterDataProvider()
        ob = OrderBook(
            symbol="BTC/USDT",
            bids=(OrderBookLevel(price=50000, quantity=10),),
            asks=(OrderBookLevel(price=50010, quantity=10),),
            timestamp=datetime.now(timezone.utc),
        )
        # Bid depth = 500000, ask depth = 500100, min = 500000
        # Notional 50000 → ratio = 0.1 → score = 0.9
        score = provider.compute_liquidity_score(ob, 50000)
        assert 0.85 < score < 0.95

        # Zero notional → score 1.0
        assert provider.compute_liquidity_score(ob, 0) == 1.0

    def test_is_funding_rate_extreme(self) -> None:
        from aiswarm.data.providers.aster import FundingRate

        provider = AsterDataProvider()

        # Extreme positive → short signal
        fr = FundingRate(
            symbol="BTC/USDT",
            funding_rate=0.002,
            mark_price=50000,
            next_funding_time=None,
            timestamp=datetime.now(timezone.utc),
        )
        extreme, direction = provider.is_funding_rate_extreme(fr)
        assert extreme
        assert direction == "short"

        # Normal funding → no signal
        fr_normal = FundingRate(
            symbol="BTC/USDT",
            funding_rate=0.0001,
            mark_price=50000,
            next_funding_time=None,
            timestamp=datetime.now(timezone.utc),
        )
        extreme, direction = provider.is_funding_rate_extreme(fr_normal)
        assert not extreme
