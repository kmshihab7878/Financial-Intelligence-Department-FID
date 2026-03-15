"""Tests for trading agents (funding rate + momentum)."""

from __future__ import annotations


from aiswarm.agents.market_intelligence.funding_rate_agent import FundingRateAgent
from aiswarm.agents.strategy.momentum_agent import MomentumAgent


class TestFundingRateAgent:
    def test_extreme_positive_funding_generates_short_signal(self) -> None:
        agent = FundingRateAgent()
        context = {
            "funding_data": {
                "symbol": "BTCUSDT",
                "lastFundingRate": "0.002",
                "markPrice": "50000",
                "nextFundingTime": 0,
            },
            "symbol": "BTCUSDT",
        }
        result = agent.analyze(context)
        signal = result["signal"]
        assert signal is not None
        assert signal.direction == -1  # Short
        assert signal.strategy == "funding_rate_contrarian"

    def test_extreme_negative_funding_generates_long_signal(self) -> None:
        agent = FundingRateAgent()
        context = {
            "funding_data": {
                "symbol": "BTCUSDT",
                "lastFundingRate": "-0.002",
                "markPrice": "50000",
                "nextFundingTime": 0,
            },
            "symbol": "BTCUSDT",
        }
        result = agent.analyze(context)
        signal = result["signal"]
        assert signal is not None
        assert signal.direction == 1  # Long

    def test_normal_funding_no_signal(self) -> None:
        agent = FundingRateAgent()
        context = {
            "funding_data": {
                "symbol": "BTCUSDT",
                "lastFundingRate": "0.0001",
                "markPrice": "50000",
                "nextFundingTime": 0,
            },
            "symbol": "BTCUSDT",
        }
        result = agent.analyze(context)
        assert result["signal"] is None

    def test_no_data_no_signal(self) -> None:
        agent = FundingRateAgent()
        result = agent.analyze({})
        assert result["signal"] is None

    def test_validate(self) -> None:
        agent = FundingRateAgent()
        assert not agent.validate({})
        assert agent.validate({"funding_data": {"lastFundingRate": "0.001"}})


class TestMomentumAgent:
    @staticmethod
    def _make_klines(prices: list[float]) -> list[dict[str, str]]:
        """Create mock kline data from a list of close prices."""
        klines = []
        for i, price in enumerate(prices):
            klines.append(
                {
                    "openTime": str(1700000000000 + i * 3600000),
                    "open": str(price * 0.999),
                    "high": str(price * 1.01),
                    "low": str(price * 0.99),
                    "close": str(price),
                    "volume": "1000",
                }
            )
        return klines

    def test_bullish_momentum_generates_long_signal(self) -> None:
        agent = MomentumAgent(fast_period=5, slow_period=10, min_candles=10)
        # Clear uptrend: prices increasing
        prices = [100 + i * 2 for i in range(20)]  # 100, 102, 104, ... 138
        context = {
            "klines_data": self._make_klines(prices),
            "symbol": "BTCUSDT",
        }
        result = agent.analyze(context)
        signal = result["signal"]
        assert signal is not None
        assert signal.direction == 1  # Long

    def test_bearish_momentum_generates_short_signal(self) -> None:
        agent = MomentumAgent(fast_period=5, slow_period=10, min_candles=10)
        # Clear downtrend: prices decreasing
        prices = [200 - i * 2 for i in range(20)]  # 200, 198, 196, ... 162
        context = {
            "klines_data": self._make_klines(prices),
            "symbol": "ETHUSDT",
        }
        result = agent.analyze(context)
        signal = result["signal"]
        assert signal is not None
        assert signal.direction == -1  # Short

    def test_insufficient_data_no_signal(self) -> None:
        agent = MomentumAgent(min_candles=50)
        context = {
            "klines_data": self._make_klines([100, 101, 102]),
            "symbol": "BTCUSDT",
        }
        result = agent.analyze(context)
        assert result["signal"] is None

    def test_no_data_no_signal(self) -> None:
        agent = MomentumAgent()
        result = agent.analyze({})
        assert result["signal"] is None

    def test_validate(self) -> None:
        agent = MomentumAgent(min_candles=5)
        assert not agent.validate({})
        prices = [100 + i for i in range(10)]
        assert agent.validate(
            {
                "klines_data": TestMomentumAgent._make_klines(prices),
                "symbol": "BTCUSDT",
            }
        )
