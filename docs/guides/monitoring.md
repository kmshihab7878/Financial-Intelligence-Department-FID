# Monitoring

AIS provides comprehensive observability through Prometheus metrics, Grafana dashboards, and structured logging.

## Stack Overview

| Component | Purpose | Port |
|-----------|---------|------|
| Prometheus | Metrics collection and storage | 9090 |
| Grafana | Dashboard visualization | 3000 |
| Alertmanager | Alert routing and notification | 9093 |
| Pushgateway | Backtest metric ingestion | 9091 |

## Prometheus Metrics

All metrics are exposed at `GET /metrics`. See the [Metrics Reference](../reference/metrics.md) for the complete list.

Key metrics to monitor:

| Metric | Alert Threshold | Meaning |
|--------|----------------|---------|
| `ais_drawdown` | > 0.04 | Approaching drawdown limit |
| `ais_leverage` | > 2.5 | High leverage |
| `ais_kill_switch_triggers_total` | > 0 | Kill switch activated |
| `ais_risk_rejections_total` | Increasing | Risk engine blocking orders |
| `ais_aster_errors_total` | Increasing | Exchange connectivity issues |

## Grafana Dashboards

Pre-built dashboards are provisioned automatically:

- **AIS Overview** — NAV, P&L, drawdown, gross/net exposure
- **Agent Performance** — Signal generation rates, latency, approval ratios
- **Execution** — Order flow, fill rates, paper trade activity
- **Risk** — Kill switch events, rejection breakdown, leverage history

Access Grafana at `http://localhost:3000` (default credentials configured via `GF_ADMIN_PASSWORD`).

## Alertmanager

Configured at `monitoring/alertmanager.yml`. Default routing sends alerts via webhook.

To add Slack notifications:

```yaml
receivers:
  - name: slack
    slack_configs:
      - api_url: ${AIS_SLACK_WEBHOOK_URL}
        channel: '#trading-alerts'
        title: 'AIS Alert'
```

## Position Reconciliation

`PositionReconciler` compares internal state against exchange data:

- **Position reconciliation** — Internal quantities vs exchange positions
- **Balance reconciliation** — Expected NAV vs exchange balance
- **Unauthorized trade detection** — Known order IDs vs exchange trades

Results are persisted as `reconciliation` events in the EventStore.

Statuses: `MATCH`, `MISMATCH`, `MISSING_INTERNAL`, `MISSING_EXCHANGE`, `ERROR`

## Resilience Monitoring

### Circuit Breaker

Per-service circuit breakers track failure rates:

- **Closed** — Normal operation
- **Open** — Service failing, requests rejected
- **Half-open** — Probing for recovery

### Rate Limiter

Token-bucket rate limiters prevent exchange API abuse. Monitor via `limiter.stats()`.

## Structured Logging

All logs are structured JSON via `aiswarm.utils.logging`:

```json
{
  "level": "INFO",
  "logger": "aiswarm.orchestration.coordinator",
  "message": "Cycle completed",
  "extra_json": {
    "cycle": 42,
    "signals_generated": 2,
    "signal_selected": true,
    "risk_approved": true,
    "duration_ms": 245
  }
}
```

Decision audit trail: JSONL files at the configured `decision_log_path`.
