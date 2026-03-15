"""Statistical drift detection methods.

Detects distributional shifts (concept drift) in time-series data
using multiple complementary methods:
- Kolmogorov-Smirnov (KS) test: nonparametric distribution comparison
- Population Stability Index (PSI): binned distribution divergence
- CUSUM: cumulative sum control chart for mean shifts
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats


@dataclass(frozen=True)
class DriftResult:
    """Result of a drift detection test."""

    drift_detected: bool
    score: float
    method: str
    details: dict[str, float | str]


def ks_drift_test(
    reference: np.ndarray,
    current: np.ndarray,
    threshold: float = 0.05,
) -> DriftResult:
    """Kolmogorov-Smirnov test for distributional drift.

    Compares two samples to determine if they come from the same distribution.

    Args:
        reference: Historical/baseline data.
        current: Recent data to test for drift.
        threshold: p-value threshold below which drift is detected.

    Returns:
        DriftResult with KS statistic and p-value.
    """
    if len(reference) < 10 or len(current) < 10:
        return DriftResult(
            drift_detected=False,
            score=0.0,
            method="ks_test",
            details={"reason": "insufficient_data"},
        )

    ks_stat, p_value = stats.ks_2samp(reference, current)

    return DriftResult(
        drift_detected=p_value < threshold,
        score=float(ks_stat),
        method="ks_test",
        details={
            "ks_statistic": float(ks_stat),
            "p_value": float(p_value),
            "threshold": threshold,
        },
    )


def population_stability_index(
    expected: np.ndarray,
    actual: np.ndarray,
    n_bins: int = 10,
) -> float:
    """Calculate Population Stability Index (PSI).

    PSI measures how much a distribution has shifted.
    - PSI < 0.1: no significant shift
    - 0.1 < PSI < 0.2: moderate shift
    - PSI > 0.2: significant shift

    Args:
        expected: Baseline distribution.
        actual: Current distribution.
        n_bins: Number of bins for histogram comparison.

    Returns:
        PSI value (non-negative).
    """
    all_data = np.concatenate([expected, actual])
    bins = np.histogram(all_data, bins=n_bins)[1]

    expected_pcts = np.histogram(expected, bins=bins)[0] / len(expected)
    actual_pcts = np.histogram(actual, bins=bins)[0] / len(actual)

    # Avoid division by zero
    expected_pcts = np.where(expected_pcts == 0, 0.001, expected_pcts)
    actual_pcts = np.where(actual_pcts == 0, 0.001, actual_pcts)

    psi_values = (actual_pcts - expected_pcts) * np.log(actual_pcts / expected_pcts)
    return float(np.sum(psi_values))


def psi_drift_test(
    reference: np.ndarray,
    current: np.ndarray,
    threshold: float = 0.2,
    n_bins: int = 10,
) -> DriftResult:
    """PSI-based drift test.

    Args:
        reference: Baseline distribution.
        current: Current distribution to test.
        threshold: PSI threshold for drift detection (default 0.2).
        n_bins: Number of bins.

    Returns:
        DriftResult with PSI score.
    """
    if len(reference) < 10 or len(current) < 10:
        return DriftResult(
            drift_detected=False,
            score=0.0,
            method="psi",
            details={"reason": "insufficient_data"},
        )

    psi = population_stability_index(reference, current, n_bins)

    return DriftResult(
        drift_detected=psi > threshold,
        score=psi,
        method="psi",
        details={"psi": psi, "threshold": threshold},
    )


def cusum_test(
    data: np.ndarray,
    target_mean: float | None = None,
    threshold: float = 5.0,
    drift_allowance: float = 0.5,
) -> DriftResult:
    """CUSUM (Cumulative Sum) control chart for mean shift detection.

    Detects persistent shifts in the mean of a process.

    Args:
        data: Time-series data.
        target_mean: Expected mean (defaults to first-half mean).
        threshold: CUSUM threshold for detecting a shift.
        drift_allowance: Slack parameter to reduce false positives.

    Returns:
        DriftResult with CUSUM statistics.
    """
    if len(data) < 20:
        return DriftResult(
            drift_detected=False,
            score=0.0,
            method="cusum",
            details={"reason": "insufficient_data"},
        )

    if target_mean is None:
        target_mean = float(np.mean(data[: len(data) // 2]))

    std = float(np.std(data))
    if std == 0:
        return DriftResult(
            drift_detected=False,
            score=0.0,
            method="cusum",
            details={"reason": "zero_variance"},
        )

    # Normalize
    normalized = (data - target_mean) / std

    # CUSUM accumulators
    s_pos = 0.0
    s_neg = 0.0
    max_pos = 0.0
    max_neg = 0.0

    for x in normalized:
        s_pos = max(0, s_pos + x - drift_allowance)
        s_neg = max(0, s_neg - x - drift_allowance)
        max_pos = max(max_pos, s_pos)
        max_neg = max(max_neg, s_neg)

    score = max(max_pos, max_neg)
    drift_detected = score > threshold

    return DriftResult(
        drift_detected=drift_detected,
        score=score,
        method="cusum",
        details={
            "max_positive": max_pos,
            "max_negative": max_neg,
            "threshold": threshold,
            "target_mean": target_mean,
        },
    )


def detect_drift(
    reference: np.ndarray,
    current: np.ndarray,
    ks_threshold: float = 0.05,
    psi_threshold: float = 0.2,
) -> DriftResult:
    """Run both KS and PSI drift tests and return combined result.

    Drift is detected if EITHER test triggers.
    """
    ks = ks_drift_test(reference, current, ks_threshold)
    psi = psi_drift_test(reference, current, psi_threshold)

    drift_detected = ks.drift_detected or psi.drift_detected
    method = "combined"
    if ks.drift_detected and psi.drift_detected:
        method = "ks+psi"
    elif ks.drift_detected:
        method = "ks_test"
    elif psi.drift_detected:
        method = "psi"

    return DriftResult(
        drift_detected=drift_detected,
        score=max(ks.score, psi.score),
        method=method,
        details={
            "ks_statistic": ks.details.get("ks_statistic", 0),
            "ks_p_value": ks.details.get("p_value", 1.0),
            "psi": psi.details.get("psi", 0),
        },
    )
