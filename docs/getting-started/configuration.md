# Configuration

AIS uses YAML configuration files in `config/` and environment variables.

## Configuration Files

| File | Purpose |
|------|---------|
| `base.yaml` | Core system settings (loop interval, log level) |
| `risk.yaml` | Risk limits, drawdown thresholds, leverage caps |
| `execution.yaml` | Execution mode, order routing |
| `exchanges.yaml` | Multi-exchange routing and credentials |
| `integrations.yaml` | TradingView, portfolio trackers, tax export |
| `mandates.yaml` | Strategy mandates, allowed assets, allocation limits |
| `monitoring.yaml` | Alerting, metrics, reconciliation |
| `portfolio.yaml` | Portfolio constraints, rebalancing rules |

## Execution Modes

| Mode | Description | Exchange Connection | Requires |
|------|-------------|-------------------|----------|
| `paper` | Simulated fills | None | `AIS_RISK_HMAC_SECRET` |
| `shadow` | Real data, simulated fills | Read-only | + `AIS_MCP_SERVER_URL` |
| `live` | Real orders | Full | + `AIS_ENABLE_LIVE_TRADING=true`, `AIS_API_KEY` |

Set via `AIS_EXECUTION_MODE` environment variable.

## Risk Configuration

```yaml
# config/risk.yaml
risk:
  max_drawdown: 0.05          # 5% rolling drawdown limit
  max_leverage: 3.0           # 3x leverage ceiling
  max_position_weight: 0.10   # 10% of NAV per position
  max_gross_exposure: 1.5     # 150% gross exposure
  min_liquidity_score: 0.3    # Minimum liquidity for approval
  kill_switch_loss: 0.03      # 3% daily loss triggers kill switch
```

## Mandate Configuration

Mandates define what each strategy is allowed to do:

```yaml
# config/mandates.yaml
mandates:
  - strategy: momentum_ma_crossover
    max_allocation: 0.10       # 10% of NAV
    allowed_symbols:
      - BTCUSDT
      - ETHUSDT
    max_position_count: 2

  - strategy: funding_rate_contrarian
    max_allocation: 0.05
    allowed_symbols:
      - BTCUSDT
    max_position_count: 1
```

## Exchange Configuration

```yaml
# config/exchanges.yaml
exchanges:
  aster:
    enabled: true
    asset_classes: [spot, futures]
    symbols: [BTCUSDT, ETHUSDT]

  binance:
    enabled: false
    asset_classes: [spot, futures]
    symbols: [SOLUSDT]
```

See the [Multi-Exchange Guide](../guides/multi-exchange.md) for details.

## Environment Variables

See the [full environment variable reference](../reference/configuration.md) for all supported variables.

### Generating Secrets

```bash
# HMAC secret
export AIS_RISK_HMAC_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# API key
export AIS_API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
```

## CLI Options

```bash
python -m aiswarm --help

# Common usage
python -m aiswarm --mode paper                       # Paper trading
python -m aiswarm --mode paper --exchange aster       # Single exchange
python -m aiswarm --mode paper --exchanges aster,binance  # Multi-exchange
python -m aiswarm --tradingview-port 8001             # Enable TradingView webhooks
python -m aiswarm --config /path/to/config/           # Custom config directory
```
