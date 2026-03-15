# Evolution Framework

## Overview

The evolution framework enables the system to improve over time by mutating strategies, challenging incumbents, detecting drift, and rolling back failed changes. Located in `src/aiswarm/evolution/`.

## Components

### Drift Detection (`evolution/drift.py`)

Detects when market conditions have shifted enough to invalidate current strategy assumptions. See also `aiswarm.quant.drift` for statistical implementations.

Available methods:
- **Kolmogorov-Smirnov test**: Nonparametric distribution comparison (p-value threshold)
- **Population Stability Index**: Binned distribution divergence (PSI < 0.1: stable, > 0.2: significant drift)
- **CUSUM**: Cumulative sum control chart for mean shift detection

### Strategy Mutation (`evolution/mutation.py`)

Generates parameter variations of existing strategies to explore the strategy space. Mutations are deployed as challengers against the incumbent.

### Challenger Framework (`evolution/challenger.py`)

Champion/challenger pattern for strategy promotion:

1. **Champion**: Currently deployed strategy with live allocation
2. **Challenger**: Mutated or new strategy running in shadow mode
3. **Evaluation**: Compare risk-adjusted returns over evaluation window
4. **Promotion**: Challenger replaces champion if statistically significant improvement

### Rollback (`evolution/rollback.py`)

Reverts strategy changes when:
- Challenger underperforms during evaluation
- Drift is detected post-promotion
- Risk limits are breached after a strategy change

## Quantitative Tools (`quant/`)

Extracted from FID research system, domain-agnostic implementations:

### Kelly Criterion (`quant/kelly.py`)
- `kelly_fraction(win_prob, payout_ratio)` -- optimal bet sizing
- `half_kelly(win_prob, payout_ratio)` -- conservative variant
- `kelly_position_size(win_prob, payout_ratio, capital, max_position_pct)` -- constrained sizing
- `expected_value()`, `variance()`, `sharpe_ratio()`

### Risk Metrics (`quant/risk_metrics.py`)
- `compute_risk_metrics(returns)` -- comprehensive suite: mean return, volatility, Sharpe, Sortino, VaR (95%), CVaR, max drawdown, skewness, kurtosis
- `parametric_var(mean, std, confidence)` -- Gaussian VaR
- `parametric_es(mean, std, confidence)` -- Expected Shortfall
- `monte_carlo_var(returns, n_simulations, horizon)` -- bootstrap MC VaR with percentile distribution

### Drift Detection (`quant/drift.py`)
- `ks_drift_test(reference, current)` -- KS test
- `psi_drift_test(reference, current)` -- PSI test
- `cusum_test(data, target_mean)` -- CUSUM control chart
- `detect_drift(reference, current)` -- combined KS + PSI

## Status

Evolution module stubs exist. The `quant/` implementations are complete and tested. The champion/challenger workflow, mutation engine, and rollback logic are planned for Phase 4.
