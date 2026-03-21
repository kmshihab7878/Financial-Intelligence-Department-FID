# Quantitative Tools

AIS includes a suite of quantitative tools for position sizing, risk measurement, and distribution drift detection. Located in `src/aiswarm/quant/`.

## Kelly Criterion

Optimal position sizing based on edge and odds.

```python
from aiswarm.quant.kelly import kelly_fraction, half_kelly, kelly_position_size

# Full Kelly optimal bet fraction
f = kelly_fraction(win_prob=0.55, payout_ratio=2.0)  # 0.275

# Conservative half-Kelly
f_half = half_kelly(win_prob=0.55, payout_ratio=2.0)  # 0.1375

# Constrained position size
size = kelly_position_size(
    win_prob=0.55,
    payout_ratio=2.0,
    capital=100_000,
    max_position_pct=0.05
)
```

### Functions

| Function | Description |
|----------|-------------|
| `kelly_fraction(win_prob, payout_ratio)` | Full Kelly optimal fraction |
| `half_kelly(win_prob, payout_ratio)` | Half-Kelly (conservative) |
| `kelly_position_size(win_prob, payout_ratio, capital, max_position_pct)` | Dollar position size with cap |
| `expected_value(win_prob, payout_ratio)` | Expected value per unit bet |
| `variance(win_prob, payout_ratio)` | Variance per unit bet |
| `sharpe_ratio(win_prob, payout_ratio, n_bets)` | Annualized Sharpe estimate |

## Risk Metrics

Comprehensive return distribution analysis.

```python
from aiswarm.quant.risk_metrics import compute_risk_metrics, monte_carlo_var

import numpy as np
returns = np.random.normal(0.001, 0.02, 252)

# Full risk suite
metrics = compute_risk_metrics(returns)
# Returns: mean_return, volatility, sharpe, sortino, var_95, cvar_95,
#          max_drawdown, skewness, kurtosis

# Monte Carlo VaR
mc_result = monte_carlo_var(returns, n_simulations=10_000, horizon=5)
```

### Functions

| Function | Description |
|----------|-------------|
| `compute_risk_metrics(returns)` | Full suite: Sharpe, Sortino, VaR, CVaR, drawdown |
| `parametric_var(mean, std, confidence)` | Gaussian Value at Risk |
| `parametric_es(mean, std, confidence)` | Expected Shortfall (CVaR) |
| `monte_carlo_var(returns, n_simulations, horizon)` | Bootstrap Monte Carlo VaR |

## Drift Detection

Statistical tests for detecting distribution shifts in market data.

```python
from aiswarm.quant.drift import detect_drift, ks_drift_test, psi_drift_test

reference_returns = np.random.normal(0.001, 0.02, 100)
current_returns = np.random.normal(0.003, 0.03, 100)

# Combined assessment
result = detect_drift(reference_returns, current_returns)
# result.ks_significant, result.psi_value, result.drift_detected

# Individual tests
ks = ks_drift_test(reference_returns, current_returns)
psi = psi_drift_test(reference_returns, current_returns)
```

### PSI Interpretation

| PSI Value | Interpretation |
|-----------|---------------|
| < 0.1 | No significant drift |
| 0.1 - 0.2 | Moderate drift, monitor closely |
| > 0.2 | Significant drift, strategy review recommended |

### Functions

| Function | Description |
|----------|-------------|
| `ks_drift_test(reference, current)` | Kolmogorov-Smirnov two-sample test |
| `psi_drift_test(reference, current)` | Population Stability Index |
| `cusum_test(data, target_mean)` | CUSUM control chart for mean shift |
| `detect_drift(reference, current)` | Combined KS + PSI assessment |

## Usage in AIS

The risk engine uses these tools during order validation:

1. **Position sizing** — Kelly criterion determines optimal position size given strategy win rate and payout ratio
2. **Risk assessment** — VaR and CVaR estimates feed into drawdown and leverage checks
3. **Regime monitoring** — Drift detection flags when market conditions diverge from strategy assumptions
