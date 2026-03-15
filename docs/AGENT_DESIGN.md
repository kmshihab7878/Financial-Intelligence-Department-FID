# Agent Design

## Architecture

Agents are the intelligence layer of AIS. Each agent consumes market data, produces `Signal` objects, and participates in a governed orchestration pipeline.

### Base Interface

All agents extend `aiswarm.agents.base.Agent` (ABC):

```
Agent(agent_id, cluster)
  .analyze(context)  -> dict   # Read and interpret data
  .propose(context)  -> dict   # Generate a Signal
  .validate(context) -> bool   # Self-check before emitting
```

### Agent Clusters

Agents are organized into functional clusters:

| Cluster | Directory | Purpose |
|---------|-----------|---------|
| `market_intelligence` | `agents/market_intelligence/` | Real-time market structure analysis |
| `strategy` | `agents/strategy/` | Signal generation from market data |

### Implemented Agents

**FundingRateAgent** (`agents/market_intelligence/funding_rate_agent.py`):
- Consumes funding rate data from Aster DEX (`get_funding_rate`)
- Detects extreme funding rates (>0.1% per 8h) as contrarian signals
- Emits long signal when funding is extremely negative, short when extremely positive

**MomentumAgent** (`agents/strategy/momentum_agent.py`):
- Consumes OHLCV candle data from Aster DEX (`get_klines`)
- Dual SMA crossover (fast_period=20, slow_period=50)
- Scores confidence by trend consistency across recent candles

## Signal Lifecycle

```
Agent.analyze(context)
  -> Agent.propose(context)
    -> Signal(signal_id, agent_id, symbol, direction, confidence, ...)
      -> WeightedArbitration.select_signal(signals)
        -> Coordinator.coordinate(signals)
          -> RiskEngine.validate(order)
```

### Signal Schema

```python
Signal(
    signal_id: str,          # Unique identifier
    agent_id: str,           # Originating agent
    symbol: str,             # Trading instrument
    strategy: str,           # Strategy name
    thesis: str,             # Human-readable rationale (min 5 chars)
    direction: int,          # -1 (short), 0 (neutral), 1 (long)
    confidence: float,       # 0.0 to 1.0
    expected_return: float,  # Expected return over horizon
    horizon_minutes: int,    # Signal validity window
    liquidity_score: float,  # 0.0 to 1.0
    regime: MarketRegime,    # risk_on | risk_off | transition | stressed
    created_at: datetime,
)
```

## Arbitration

`WeightedArbitration` selects the best signal from competing agents using:

```
score = agent_weight * confidence * max(expected_return, 0) * max(liquidity_score, 0.01)
```

Winner-take-all: only the highest-scoring signal proceeds to allocation.

## Adding a New Agent

1. Create a module in the appropriate cluster directory
2. Extend `Agent` base class, implement `analyze()`, `propose()`, `validate()`
3. `propose()` must return a `Signal` with all required fields
4. Register the agent with the `Coordinator` at startup
5. Set agent weight in arbitration config
