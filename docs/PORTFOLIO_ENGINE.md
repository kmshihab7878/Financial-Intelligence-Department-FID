# Portfolio Engine

## Components

### Portfolio Allocator (`portfolio/allocator.py`)

Converts signals into orders using target weight sizing:

```python
PortfolioAllocator(target_weight=0.02)
  .order_from_signal(signal, snapshot) -> Order
```

**Sizing formula**:
```
notional = max(nav * target_weight * confidence, 100.0)
quantity = notional / price_proxy
```

- `target_weight`: Fraction of NAV per position (default 2%)
- `confidence`: Signal confidence (0.0-1.0) scales position down
- Direction: `signal.direction >= 0` -> BUY, else SELL

### Exposure Manager (`portfolio/exposure.py`)

Validates portfolio-level exposure limits before risk approval:

- **Max position weight**: Single position cannot exceed X% of NAV
- **Max gross exposure**: Sum of all position absolute values cannot exceed X% of NAV

### SharedMemory (`orchestration/memory.py`)

Maintains live portfolio state for the coordinator:

| Field | Description |
|-------|-------------|
| `latest_snapshot` | Current `PortfolioSnapshot` |
| `latest_pnl` | Daily P&L fraction |
| `rolling_drawdown` | Peak-to-trough drawdown |
| `current_leverage` | Gross exposure / NAV |
| `peak_nav` | Highest NAV observed |

`update_snapshot(snapshot)` automatically derives drawdown and leverage from the snapshot.

## Data Flow

```
Signal
  -> PortfolioAllocator.order_from_signal(signal, snapshot)
    -> Order(notional, quantity, side)
      -> RiskEngine.validate()
        -> ExposureManager.check_order(order, snapshot)
        -> DrawdownGuard, LeverageGuard, LiquidityGuard
```

## Position Reconciliation

`PositionReconciler` (in `monitoring/reconciliation.py`) compares `SharedMemory.latest_snapshot` against real positions from Aster DEX. See `MONITORING_AND_OBSERVABILITY.md`.

## State Persistence

Portfolio checkpoints are saved to the EventStore:
- `EventStore.save_portfolio_checkpoint(snapshot_dict)`
- `EventStore.load_portfolio_checkpoint()` for recovery after restart
