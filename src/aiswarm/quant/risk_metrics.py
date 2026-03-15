"""Risk metrics: VaR, CVaR, Sharpe, Sortino, Monte Carlo simulation.

Domain-agnostic implementations suitable for any return series.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import norm


@dataclass(frozen=True)
class RiskMetrics:
    """Computed risk metrics for a return series."""

    mean_return: float
    volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    var_95: float
    cvar_95: float
    max_drawdown: float
    skewness: float
    kurtosis: float


def compute_risk_metrics(
    returns: np.ndarray,
    risk_free_rate: float = 0.0,
) -> RiskMetrics:
    """Compute comprehensive risk metrics from a return series.

    Args:
        returns: Array of period returns (e.g. daily returns).
        risk_free_rate: Risk-free rate per period (default 0).

    Returns:
        RiskMetrics dataclass with all computed values.
    """
    if len(returns) < 2:
        return RiskMetrics(
            mean_return=0.0,
            volatility=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            var_95=0.0,
            cvar_95=0.0,
            max_drawdown=0.0,
            skewness=0.0,
            kurtosis=0.0,
        )

    mean_ret = float(np.mean(returns))
    vol = float(np.std(returns, ddof=1))

    # Sharpe ratio
    sharpe = (mean_ret - risk_free_rate) / vol if vol > 0 else 0.0

    # Sortino ratio (downside deviation only)
    downside = returns[returns < risk_free_rate] - risk_free_rate
    downside_vol = float(np.std(downside, ddof=1)) if len(downside) > 1 else vol
    sortino = (mean_ret - risk_free_rate) / downside_vol if downside_vol > 0 else 0.0

    # VaR (95% historical)
    var_95 = float(np.percentile(returns, 5))

    # CVaR / Expected Shortfall (average of losses beyond VaR)
    tail = returns[returns <= var_95]
    cvar_95 = float(np.mean(tail)) if len(tail) > 0 else var_95

    # Max drawdown
    cumulative = np.cumprod(1 + returns)
    peak = np.maximum.accumulate(cumulative)
    drawdowns = (peak - cumulative) / peak
    max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    # Higher moments
    skew = float(np.mean(((returns - mean_ret) / vol) ** 3)) if vol > 0 else 0.0
    kurt = float(np.mean(((returns - mean_ret) / vol) ** 4) - 3) if vol > 0 else 0.0

    return RiskMetrics(
        mean_return=mean_ret,
        volatility=vol,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        var_95=var_95,
        cvar_95=cvar_95,
        max_drawdown=max_dd,
        skewness=skew,
        kurtosis=kurt,
    )


def parametric_var(
    mean: float,
    std: float,
    confidence: float = 0.95,
    position_size: float = 1.0,
) -> float:
    """Parametric (Gaussian) Value at Risk.

    Args:
        mean: Expected return.
        std: Standard deviation.
        confidence: Confidence level (e.g. 0.95 for 95% VaR).
        position_size: Position notional value.

    Returns:
        VaR as a positive loss value.
    """
    z: float = float(norm.ppf(1 - confidence))
    return -(mean + z * std) * position_size


def parametric_es(
    mean: float,
    std: float,
    confidence: float = 0.95,
    position_size: float = 1.0,
) -> float:
    """Parametric Expected Shortfall (Conditional VaR).

    Average loss given that VaR is exceeded.
    """
    z: float = float(norm.ppf(1 - confidence))
    es = -mean + std * float(norm.pdf(z)) / (1 - confidence)
    return es * position_size


def monte_carlo_var(
    returns: np.ndarray,
    n_simulations: int = 10000,
    horizon: int = 1,
    confidence: float = 0.95,
) -> dict[str, float]:
    """Monte Carlo VaR using bootstrap resampling.

    Args:
        returns: Historical return series.
        n_simulations: Number of Monte Carlo paths.
        horizon: Number of periods to simulate.
        confidence: Confidence level.

    Returns:
        Dict with var, cvar, mean, and percentiles.
    """
    if len(returns) < 10:
        return {"var": 0.0, "cvar": 0.0, "mean": 0.0}

    simulated_returns = np.zeros(n_simulations)
    for i in range(n_simulations):
        sampled = np.random.choice(returns, size=horizon, replace=True)
        simulated_returns[i] = float(np.prod(1 + sampled) - 1)

    var_level = np.percentile(simulated_returns, (1 - confidence) * 100)
    tail = simulated_returns[simulated_returns <= var_level]
    cvar = float(np.mean(tail)) if len(tail) > 0 else float(var_level)

    return {
        "var": float(var_level),
        "cvar": cvar,
        "mean": float(np.mean(simulated_returns)),
        "std": float(np.std(simulated_returns)),
        "p5": float(np.percentile(simulated_returns, 5)),
        "p25": float(np.percentile(simulated_returns, 25)),
        "p50": float(np.percentile(simulated_returns, 50)),
        "p75": float(np.percentile(simulated_returns, 75)),
        "p95": float(np.percentile(simulated_returns, 95)),
    }
