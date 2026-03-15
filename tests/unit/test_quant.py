"""Tests for the quant module: Kelly, drift detection, risk metrics."""

from __future__ import annotations

import numpy as np
import pytest

scipy = pytest.importorskip("scipy", reason="scipy required for quant drift tests")

from aiswarm.quant.drift import (  # noqa: E402
    cusum_test,
    detect_drift,
    ks_drift_test,
    population_stability_index,
    psi_drift_test,
)
from aiswarm.quant.kelly import (  # noqa: E402
    expected_value,
    half_kelly,
    kelly_fraction,
    kelly_position_size,
    variance,
)
from aiswarm.quant.risk_metrics import (  # noqa: E402
    compute_risk_metrics,
    monte_carlo_var,
    parametric_es,
    parametric_var,
)


# --- Kelly Criterion ---


class TestKelly:
    def test_fair_coin_even_payoff(self) -> None:
        # 50% win, 2x payout: f* = (1*0.5 - 0.5)/1 = 0
        f = kelly_fraction(0.5, 2.0)
        assert abs(f) < 1e-9

    def test_edge_positive(self) -> None:
        # 60% win, 2x payout: f* = (1*0.6 - 0.4)/1 = 0.2
        f = kelly_fraction(0.6, 2.0)
        assert abs(f - 0.2) < 1e-9

    def test_negative_edge_returns_negative(self) -> None:
        f = kelly_fraction(0.3, 2.0)
        assert f < 0

    def test_payout_below_one_returns_zero(self) -> None:
        f = kelly_fraction(0.6, 0.9)
        assert f == 0.0

    def test_half_kelly(self) -> None:
        full = kelly_fraction(0.6, 2.0)
        half = half_kelly(0.6, 2.0)
        assert abs(half - full * 0.5) < 1e-9

    def test_position_size_with_edge(self) -> None:
        size = kelly_position_size(0.6, 2.0, capital=100_000, max_position_pct=0.05)
        assert size > 0
        assert size <= 100_000 * 0.05

    def test_position_size_no_edge(self) -> None:
        size = kelly_position_size(0.3, 2.0, capital=100_000)
        assert size == 0.0

    def test_expected_value(self) -> None:
        ev = expected_value(0.6, 2.0)
        # 0.6 * 2.0 - 0.4 = 0.8
        assert abs(ev - 0.8) < 1e-9

    def test_variance(self) -> None:
        v = variance(0.5, 2.0)
        assert v > 0


# --- Drift Detection ---


class TestDriftDetection:
    def test_ks_no_drift_identical(self) -> None:
        rng = np.random.default_rng(42)
        data = rng.normal(0, 1, 200)
        result = ks_drift_test(data[:100], data[100:])
        assert not result.drift_detected

    def test_ks_drift_detected_shifted(self) -> None:
        rng = np.random.default_rng(42)
        ref = rng.normal(0, 1, 200)
        shifted = rng.normal(3, 1, 200)
        result = ks_drift_test(ref, shifted)
        assert result.drift_detected
        assert result.score > 0

    def test_ks_insufficient_data(self) -> None:
        result = ks_drift_test(np.array([1.0, 2.0]), np.array([3.0]))
        assert not result.drift_detected
        assert result.score == 0.0

    def test_psi_no_drift(self) -> None:
        rng = np.random.default_rng(42)
        data = rng.normal(0, 1, 2000)
        psi = population_stability_index(data[:1000], data[1000:])
        assert psi < 0.2

    def test_psi_drift_detected(self) -> None:
        rng = np.random.default_rng(42)
        ref = rng.normal(0, 1, 500)
        shifted = rng.normal(3, 1, 500)
        result = psi_drift_test(ref, shifted)
        assert result.drift_detected

    def test_cusum_no_drift(self) -> None:
        rng = np.random.default_rng(42)
        data = rng.normal(0, 1, 100)
        result = cusum_test(data, threshold=10.0)
        assert not result.drift_detected

    def test_cusum_drift_detected(self) -> None:
        rng = np.random.default_rng(42)
        stable = rng.normal(0, 1, 50)
        shifted = rng.normal(5, 1, 50)
        data = np.concatenate([stable, shifted])
        result = cusum_test(data, threshold=5.0)
        assert result.drift_detected

    def test_cusum_insufficient_data(self) -> None:
        result = cusum_test(np.array([1.0, 2.0, 3.0]))
        assert not result.drift_detected

    def test_detect_drift_combined(self) -> None:
        rng = np.random.default_rng(42)
        ref = rng.normal(0, 1, 200)
        shifted = rng.normal(3, 1, 200)
        result = detect_drift(ref, shifted)
        assert result.drift_detected
        assert "ks" in result.method or "psi" in result.method


# --- Risk Metrics ---


class TestRiskMetrics:
    def test_compute_basic_metrics(self) -> None:
        rng = np.random.default_rng(42)
        returns = rng.normal(0.001, 0.02, 252)
        metrics = compute_risk_metrics(returns)

        assert metrics.mean_return != 0
        assert metrics.volatility > 0
        assert metrics.var_95 < 0  # 5th percentile of returns should be negative
        assert metrics.cvar_95 <= metrics.var_95
        assert 0 <= metrics.max_drawdown <= 1

    def test_insufficient_data(self) -> None:
        metrics = compute_risk_metrics(np.array([0.01]))
        assert metrics.mean_return == 0.0
        assert metrics.volatility == 0.0

    def test_parametric_var(self) -> None:
        var = parametric_var(mean=0.001, std=0.02, confidence=0.95)
        assert var > 0  # VaR is a positive loss value

    def test_parametric_es(self) -> None:
        es = parametric_es(mean=0.001, std=0.02, confidence=0.95)
        var = parametric_var(mean=0.001, std=0.02, confidence=0.95)
        assert es > var  # ES should exceed VaR

    def test_monte_carlo_var(self) -> None:
        rng = np.random.default_rng(42)
        returns = rng.normal(0.001, 0.02, 252)
        result = monte_carlo_var(returns, n_simulations=1000, horizon=5)

        assert "var" in result
        assert "cvar" in result
        assert "mean" in result
        assert result["cvar"] <= result["var"]

    def test_monte_carlo_insufficient_data(self) -> None:
        result = monte_carlo_var(np.array([0.01, 0.02]))
        assert result["var"] == 0.0
