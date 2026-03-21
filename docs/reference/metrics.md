# Metrics Reference

All metrics are exposed at `GET /metrics` in Prometheus format and scraped by the bundled Prometheus instance.

## Portfolio Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `ais_pnl` | Gauge | Portfolio P&L fraction |
| `ais_exposure` | Gauge | Gross exposure fraction |
| `ais_nav` | Gauge | Net asset value in quote currency |
| `ais_drawdown` | Gauge | Current rolling drawdown fraction |
| `ais_leverage` | Gauge | Current portfolio leverage |

## Agent Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `ais_agent_latency_seconds` | Histogram | `agent_id` | Agent analysis latency |
| `ais_signals_total` | Counter | `agent_id`, `direction` | Total signals generated |
| `ais_signals_approved_total` | Counter | — | Signals that passed risk |
| `ais_signals_rejected_total` | Counter | `reason` | Signals rejected by risk engine |

## Execution Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `ais_orders_submitted_total` | Counter | `symbol`, `side` | Orders submitted to OMS |
| `ais_orders_filled_total` | Counter | `symbol` | Orders filled |
| `ais_paper_fills_total` | Counter | `symbol` | Paper trading fills |

## Exchange Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `ais_aster_latency_seconds` | Histogram | `tool` | MCP call latency |
| `ais_aster_errors_total` | Counter | `tool` | MCP call errors |
| `ais_aster_data_age_seconds` | Gauge | `data_type` | Data freshness |

## Risk Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `ais_kill_switch_triggers_total` | Counter | — | Kill switch activations |
| `ais_risk_rejections_total` | Counter | `guard` | Risk validation rejections |

## Useful PromQL Queries

```promql
# Signals approved vs rejected (last hour)
sum(rate(ais_signals_approved_total[1h]))
/
(sum(rate(ais_signals_approved_total[1h])) + sum(rate(ais_signals_rejected_total[1h])))

# Agent latency p99
histogram_quantile(0.99, rate(ais_agent_latency_seconds_bucket[5m]))

# Current drawdown
ais_drawdown

# Order submission rate by symbol
sum by (symbol) (rate(ais_orders_submitted_total[5m]))
```

## Grafana Dashboards

Pre-built dashboards are provisioned automatically via `monitoring/grafana/`:

- **AIS Overview** — NAV, P&L, drawdown, exposure
- **Agent Performance** — Signal generation rates, latency, approval ratios
- **Execution** — Order flow, fill rates, paper trade activity
- **Risk** — Kill switch events, rejection reasons, leverage
