"""Kelly criterion position sizing.

The Kelly criterion determines the optimal fraction of capital to risk
on a given opportunity to maximize long-run geometric growth rate.

f* = (b*p - q) / b

Where:
  b = net odds (payout - 1)
  p = probability of winning
  q = probability of losing (1 - p)
"""

from __future__ import annotations

import math


def kelly_fraction(
    win_prob: float,
    payout_ratio: float,
) -> float:
    """Calculate the Kelly fraction for a binary outcome.

    Args:
        win_prob: Probability of winning (0-1).
        payout_ratio: Gross payout per unit risked (e.g. 2.0 means 2x return).

    Returns:
        Optimal fraction of capital to risk. Can be negative (don't bet).
    """
    if payout_ratio <= 1.0:
        return 0.0
    b = payout_ratio - 1.0
    q = 1.0 - win_prob
    return (b * win_prob - q) / b


def half_kelly(win_prob: float, payout_ratio: float) -> float:
    """Half-Kelly: more conservative, reduces variance at cost of lower growth."""
    return kelly_fraction(win_prob, payout_ratio) * 0.5


def kelly_position_size(
    win_prob: float,
    payout_ratio: float,
    capital: float,
    max_position_pct: float = 0.05,
    min_edge: float = 0.001,
) -> float:
    """Calculate constrained position size using Kelly criterion.

    Args:
        win_prob: Probability of winning.
        payout_ratio: Gross payout per unit risked.
        capital: Total available capital.
        max_position_pct: Maximum position as fraction of capital.
        min_edge: Minimum expected value to justify a position.

    Returns:
        Dollar amount to risk.
    """
    ev = expected_value(win_prob, payout_ratio)
    if ev < min_edge:
        return 0.0

    fraction = kelly_fraction(win_prob, payout_ratio)
    if fraction <= 0:
        return 0.0

    constrained = min(fraction, max_position_pct)
    return max(0.0, constrained * capital)


def expected_value(win_prob: float, payout_ratio: float) -> float:
    """Calculate expected value per unit risked.

    EV = p * payout - (1-p) * 1
    """
    return win_prob * payout_ratio - (1.0 - win_prob)


def variance(win_prob: float, payout_ratio: float) -> float:
    """Calculate variance of outcome per unit risked."""
    ev = expected_value(win_prob, payout_ratio)
    return win_prob * (payout_ratio - ev) ** 2 + (1.0 - win_prob) * (-1.0 - ev) ** 2


def sharpe_ratio(ev: float, var: float) -> float:
    """Calculate Sharpe ratio (return / volatility)."""
    if var <= 0:
        return float("inf") if ev > 0 else 0.0
    return ev / math.sqrt(var)
