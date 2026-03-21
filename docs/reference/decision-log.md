# Decision Log

Every coordinator cycle produces a `DecisionLog` entry capturing what signals were considered, which was selected, and whether risk approved the resulting order. This provides the audit trail required for attribution, replay, and regulatory compliance.

## Schema

```python
DecisionLog(
    decision_id: str,                      # Unique ID (format: "decision_<uuid>")
    timestamp: datetime,                   # UTC timestamp of decision
    decision_type: str,                    # "order_intent"
    summary: str,                          # Human-readable summary
    agent_votes: dict[str, float],         # {agent_id: confidence}
    selected_signal_id: str | None,        # Winning signal ID
    selected_order_id: str | None,         # Resulting order ID
    risk_passed: bool,                     # Did risk engine approve?
    risk_reasons: tuple[str, ...],         # Risk check results
)
```

## Storage

Decision logs are persisted in two places:

1. **JSONL file** — Appended to the configured `decision_log_path`. One JSON object per line.
2. **Event store** — Appended as event type `"decision"` via `EventStore.append_decision()`.

## Example Entry

```json
{
  "decision_id": "decision_a1b2c3",
  "timestamp": "2026-03-12T14:30:00+00:00",
  "decision_type": "order_intent",
  "summary": "Selected BTCUSDT from funding_rate_agent",
  "agent_votes": {
    "funding_rate_agent": 0.85,
    "momentum_agent": 0.62
  },
  "selected_signal_id": "sig_x9y8z7",
  "selected_order_id": "ord_m4n5o6",
  "risk_passed": true,
  "risk_reasons": ["approved"]
}
```

## Risk Rejection Reasons

When `risk_passed` is false, `risk_reasons` contains one or more of:

| Reason | Guard | Meaning |
|--------|-------|---------|
| `kill_switch_triggered` | KillSwitch | Daily loss exceeded threshold |
| `position_too_large` | ExposureManager | Order exceeds max position weight |
| `gross_exposure_exceeded` | ExposureManager | Total exposure exceeds limit |
| `drawdown_breached: X >= Y` | DrawdownGuard | Rolling drawdown above maximum |
| `leverage_breached: X > Y` | LeverageGuard | Current leverage above maximum |
| `liquidity_insufficient: X < Y` | LiquidityGuard | Liquidity score below minimum |

## Querying

```python
from aiswarm.data.event_store import EventStore

store = EventStore()

# Recent decisions
decisions = store.get_decisions(limit=50)

# Filter by risk outcome
rejected = [d for d in decisions if not d["payload"]["risk_passed"]]

# Filter by agent
momentum_wins = [
    d for d in decisions
    if d["payload"].get("summary", "").endswith("momentum_agent")
]
```
