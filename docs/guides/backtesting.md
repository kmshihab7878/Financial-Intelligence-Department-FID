# Backtesting

AIS includes a backtesting engine for evaluating strategies against historical data.

## Overview

The backtesting engine replays historical market data through the same pipeline used in live trading. This ensures that backtested results reflect the actual system behavior, including risk validation and position sizing.

## Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Backtest Engine | `backtest/engine.py` | Core backtesting loop |
| Data Loader | `backtest/data_loader.py` | Load historical OHLCV data |
| Adapters | `backtest/adapters.py` | Connect strategies to the engine |

## Running a Backtest

```python
from aiswarm.backtest.engine import BacktestEngine
from aiswarm.backtest.data_loader import load_klines_csv
from aiswarm.agents.strategy.momentum_agent import MomentumAgent

# Load historical data
data = load_klines_csv("data/btcusdt_1h_2025.csv")

# Configure the engine
engine = BacktestEngine(
    initial_capital=100_000,
    risk_config={"max_drawdown": 0.05, "max_leverage": 3.0},
)

# Register strategies
engine.add_agent(MomentumAgent(fast_period=20, slow_period=50))

# Run backtest
results = engine.run(data)
print(f"Total return: {results.total_return:.2%}")
print(f"Sharpe ratio: {results.sharpe_ratio:.2f}")
print(f"Max drawdown: {results.max_drawdown:.2%}")
```

## Interpreting Results

Key metrics returned by the backtest engine:

| Metric | Description |
|--------|-------------|
| `total_return` | Cumulative return over the backtest period |
| `sharpe_ratio` | Risk-adjusted return (annualized) |
| `sortino_ratio` | Downside risk-adjusted return |
| `max_drawdown` | Largest peak-to-trough decline |
| `win_rate` | Fraction of profitable trades |
| `profit_factor` | Gross profit / gross loss |
| `total_trades` | Number of completed round trips |

## Data Format

Historical data should be in CSV format with OHLCV columns:

```csv
timestamp,open,high,low,close,volume
2025-01-01T00:00:00Z,42150.0,42300.0,42050.0,42200.0,1250.5
2025-01-01T01:00:00Z,42200.0,42450.0,42180.0,42380.0,980.3
```

## Best Practices

1. **Use out-of-sample data** — Never optimize on the same data you evaluate on
2. **Account for slippage** — Real fills differ from mid-price
3. **Test across regimes** — Run backtests across trending and ranging markets
4. **Compare against benchmarks** — Buy-and-hold is the minimum bar
5. **Check for overfitting** — More parameters = higher overfitting risk

## Pushing Metrics

Backtest results can be pushed to Prometheus via Pushgateway:

```bash
export AIS_PUSHGATEWAY_URL=http://localhost:9091
python -m aiswarm.backtest.run --data data/btcusdt_1h.csv --push-metrics
```
