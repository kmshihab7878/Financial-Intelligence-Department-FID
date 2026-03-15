# Monitoring and Observability

## Prometheus Metrics (`monitoring/metrics.py`)

All metrics are exposed at `GET /metrics` in Prometheus format.

### Portfolio Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `ais_pnl` | Gauge | Portfolio P&L fraction |
| `ais_exposure` | Gauge | Gross exposure fraction |
| `ais_nav` | Gauge | Net asset value in quote currency |
| `ais_drawdown` | Gauge | Current rolling drawdown fraction |
| `ais_leverage` | Gauge | Current portfolio leverage |

### Agent Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `ais_agent_latency_seconds` | Histogram | agent_id | Agent analysis latency |
| `ais_signals_total` | Counter | agent_id, direction | Total signals generated |
| `ais_signals_approved_total` | Counter | -- | Signals that passed risk |
| `ais_signals_rejected_total` | Counter | reason | Signals rejected by risk engine |

### Execution Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `ais_orders_submitted_total` | Counter | symbol, side | Orders submitted to OMS |
| `ais_orders_filled_total` | Counter | symbol | Orders filled |
| `ais_paper_fills_total` | Counter | symbol | Paper trading fills |

### Aster DEX Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `ais_aster_latency_seconds` | Histogram | tool | MCP call latency |
| `ais_aster_errors_total` | Counter | tool | MCP call errors |
| `ais_aster_data_age_seconds` | Gauge | data_type | Data freshness |

### Risk Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `ais_kill_switch_triggers_total` | Counter | -- | Kill switch activations |
| `ais_risk_rejections_total` | Counter | guard | Risk validation rejections |

## Health Check (`monitoring/health.py`)

`GET /health` returns component-level health:

```json
{
  "status": "ok",
  "aster_connected": true,
  "db_connected": true,
  "redis_connected": false
}
```

## Reconciliation (`monitoring/reconciliation.py`)

`PositionReconciler` compares internal state against Aster DEX exchange data:

- **Position reconciliation**: Internal quantities vs `get_positions`
- **Balance reconciliation**: Expected NAV vs `get_balance`
- **Unauthorized trade detection**: Known order IDs vs `get_my_trades`

Results are persisted as `reconciliation` events in the EventStore.

Reconciliation statuses: `MATCH`, `MISMATCH`, `MISSING_INTERNAL`, `MISSING_EXCHANGE`, `ERROR`.

## Resilience Observability

### Circuit Breaker (`resilience/circuit_breaker.py`)

Per-service circuit breakers track:
- State: `closed` (normal), `open` (failing), `half_open` (probing)
- Failure/success counts, total calls, total rejections

Access via `all_breaker_stats()`.

### Rate Limiter (`resilience/rate_limiter.py`)

Token-bucket limiters track:
- Tokens available, allowed/throttled counts

Access via `limiter.stats()`.

## Logging

Structured JSON logging via `aiswarm.utils.logging`. All log entries include:
- `level`, `logger`, `message`
- Optional `extra_json` for structured context

Decision audit trail: JSONL files at `decision_log_path`.

## Infrastructure

Docker Compose provides:
- **Prometheus** (port 9090): Scrapes `/metrics` every 5s
- **Grafana** (port 3000): Dashboard visualization
