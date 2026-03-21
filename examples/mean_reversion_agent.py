"""Example: Mean Reversion Strategy Agent.

This is an educational example showing how to build a custom strategy agent
for AIS. It implements a simple Bollinger Band mean-reversion strategy.

Strategy:
  - Price below lower Bollinger Band -> oversold -> long signal
  - Price above upper Bollinger Band -> overbought -> short signal
  - Confidence scales with distance from the band

To use this in AIS, register it with the Coordinator at startup.
See the Strategy Development Guide for details:
https://kmshihab7878.github.io/Autonomous-Investment-Swarm/guides/strategy-development/
"""

from __future__ import annotations

import math
from typing import Any

from aiswarm.agents.base import Agent
from aiswarm.data.providers.aster import AsterDataProvider, OHLCV
from aiswarm.types.market import MarketRegime, Signal
from aiswarm.utils.ids import new_id
from aiswarm.utils.logging import get_logger
from aiswarm.utils.time import utc_now

logger = get_logger(__name__)


def _bollinger_bands(
    candles: list[OHLCV], period: int = 20, num_std: float = 2.0
) -> tuple[float, float, float] | None:
    """Compute Bollinger Bands (middle, upper, lower)."""
    if len(candles) < period:
        return None

    closes = [c.close for c in candles[-period:]]
    middle = sum(closes) / len(closes)
    variance = sum((c - middle) ** 2 for c in closes) / len(closes)
    std = math.sqrt(variance)

    upper = middle + num_std * std
    lower = middle - num_std * std
    return middle, upper, lower


class MeanReversionAgent(Agent):
    """Generates mean-reversion signals using Bollinger Bands.

    Parameters:
        bb_period: Lookback period for Bollinger Bands (default: 20)
        bb_std: Number of standard deviations for bands (default: 2.0)
        min_candles: Minimum candles required for analysis (default: 30)
    """

    def __init__(
        self,
        agent_id: str = "mean_reversion_agent",
        cluster: str = "strategy",
        bb_period: int = 20,
        bb_std: float = 2.0,
        min_candles: int = 30,
    ) -> None:
        super().__init__(agent_id=agent_id, cluster=cluster)
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.min_candles = min_candles
        self.provider = AsterDataProvider()

    def analyze(self, context: dict[str, Any]) -> dict[str, Any]:
        """Analyze price data for mean-reversion opportunities."""
        raw_klines = context.get("klines_data")
        symbol = context.get("symbol", "BTCUSDT")

        if raw_klines is None:
            return {"signal": None, "reason": "no_klines_data"}

        candles = self.provider.parse_klines(raw_klines, symbol)
        if len(candles) < self.min_candles:
            return {"signal": None, "reason": "insufficient_data"}

        bands = _bollinger_bands(candles, self.bb_period, self.bb_std)
        if bands is None:
            return {"signal": None, "reason": "cannot_compute_bands"}

        middle, upper, lower = bands
        current_price = candles[-1].close
        band_width = upper - lower

        # Determine signal direction
        if current_price < lower:
            direction = 1  # Long: price is below lower band (oversold)
            distance = (lower - current_price) / band_width
            thesis_direction = "long"
        elif current_price > upper:
            direction = -1  # Short: price is above upper band (overbought)
            distance = (current_price - upper) / band_width
            thesis_direction = "short"
        else:
            return {
                "signal": None,
                "reason": "price_within_bands",
                "middle": middle,
                "upper": upper,
                "lower": lower,
            }

        # Confidence: higher when price is further from the band
        confidence = min(0.85, 0.45 + distance * 0.4)
        confidence = max(0.35, confidence)

        # Expected return: distance to middle band
        expected_return = abs(current_price - middle) / current_price * 0.5

        # Regime: mean reversion works better in range-bound markets
        regime = MarketRegime.RISK_OFF if band_width / middle < 0.04 else MarketRegime.TRANSITION

        signal = Signal(
            signal_id=new_id("sig"),
            agent_id=self.agent_id,
            symbol=symbol,
            strategy="mean_reversion_bb",
            thesis=(
                f"Mean reversion {thesis_direction}: price={current_price:.2f}, "
                f"lower={lower:.2f}, middle={middle:.2f}, upper={upper:.2f}"
            ),
            direction=direction,
            confidence=confidence,
            expected_return=expected_return,
            horizon_minutes=120,  # 2 hours — mean reversion has shorter horizon
            liquidity_score=0.8,
            regime=regime,
            created_at=utc_now(),
            reference_price=current_price,
        )

        logger.info(
            "Mean reversion signal generated",
            extra={
                "extra_json": {
                    "symbol": symbol,
                    "direction": thesis_direction,
                    "confidence": round(confidence, 4),
                    "distance_from_band": round(distance, 4),
                }
            },
        )

        return {
            "signal": signal,
            "middle": middle,
            "upper": upper,
            "lower": lower,
            "distance": distance,
        }

    def propose(self, context: dict[str, Any]) -> dict[str, Any]:
        """Propose action based on analysis."""
        return self.analyze(context)

    def validate(self, context: dict[str, Any]) -> bool:
        """Validate that we have sufficient data for Bollinger Band computation."""
        raw_klines = context.get("klines_data")
        if raw_klines is None:
            return False
        candles = self.provider.parse_klines(raw_klines, context.get("symbol", ""))
        return len(candles) >= self.min_candles
