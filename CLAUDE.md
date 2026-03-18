# AIS — CLAUDE.md

## Project Identity

- **Name**: Autonomous Investment Swarm
- **Owner**: Khaled Shihab (kmshihab7878)
- **Repository**: `Financial-Intelligence-Department-FID`
- **Production Track**: `src/aiswarm/` (AIS — multi-exchange risk-gated execution)

## Architecture

```
src/aiswarm/
├── agents/         # Strategy agents (momentum, funding rate)
├── api/            # FastAPI control plane (auth, routes, Prometheus)
├── backtest/       # Backtesting engine, adapters, data loader
├── bootstrap.py    # Config → component graph wiring
├── data/           # EventStore (SQLite), Aster data provider/parsers
├── exchange/       # Exchange abstraction layer
│   ├── provider.py     # ExchangeProvider ABC, AssetClass flags
│   ├── registry.py     # ExchangeRegistry (multi-exchange lookup)
│   ├── symbols.py      # SymbolRouter (symbol → exchange mapping)
│   ├── config.py       # ExchangeConfig Pydantic models
│   ├── types.py        # Canonical types (OHLCV, Ticker, OrderBook, etc.)
│   └── providers/      # Exchange implementations
│       ├── aster.py        # Aster DEX (all mcp__aster__ refs here)
│       ├── binance.py      # Binance (spot + futures)
│       ├── coinbase.py     # Coinbase (spot only)
│       ├── bybit.py        # Bybit (spot + futures + options, v5 API)
│       └── ib.py           # Interactive Brokers (stocks, options, futures, forex)
├── execution/      # LiveOrderExecutor, OrderStore, FillTracker, HTTPMCPGateway
├── integrations/   # External service integrations
│   ├── tradingview/    # Webhook ingestion → AIS Signal conversion
│   ├── portfolio_tracker/  # Export to CoinGecko, Zapper, DeBank
│   └── tax/            # CSV/Koinly/CoinTracker trade export
├── loop/           # Autonomous trading loop (60s cycle)
├── mandates/       # Governance: mandate registry, validator
├── monitoring/     # Prometheus metrics, alerts, reconciliation
├── orchestration/  # Coordinator, arbitration, SharedMemory
├── portfolio/      # Allocator, exposure manager
├── quant/          # Kelly criterion, risk metrics
├── resilience/     # Circuit breaker, rate limiter, graceful shutdown
├── review/         # Session review generator, review models
├── risk/           # RiskEngine, kill switch, drawdown, leverage, liquidity
├── session/        # Session lifecycle (schedule → approve → active → end)
├── types/          # Pydantic domain models (Signal, Order, Portfolio)
└── utils/          # Secrets provider, logging, time utilities
```

## Critical Invariants

1. **No order executes without HMAC-signed risk approval** — `RiskEngine.validate()` signs; token verified before submission
2. **Fail closed on missing secrets** — `AIS_RISK_HMAC_SECRET` and `AIS_API_KEY` (in live mode) are mandatory
3. **Mandate-strategy alignment** — config strategy names must match agent code (`momentum_ma_crossover`, `funding_rate_contrarian`)
4. **Control state via Redis** — API and loop share state through `ais:control:state` Redis key
5. **Three execution modes** — PAPER (simulated), SHADOW (read-only), LIVE (requires `AIS_ENABLE_LIVE_TRADING=true`)
6. **Provider encapsulates tool names** — All `mcp__<exchange>__*` strings live inside the exchange provider, nowhere else
7. **Config-driven symbol routing** — `config/exchanges.yaml` maps symbols to exchanges; no config defaults to Aster-only

## Development Commands

```bash
# Tests
pytest tests/unit/ --cov=src/aiswarm --cov-fail-under=83

# Lint
ruff check src/ tests/unit/
ruff format --check src/ tests/unit/

# Type check
mypy src/aiswarm/ --ignore-missing-imports

# Docker
docker compose up --build
```

## Environment Variables (Required)

| Variable | Purpose | Required When |
|----------|---------|---------------|
| `AIS_RISK_HMAC_SECRET` | HMAC key for risk token signing | Always |
| `AIS_RISK_HMAC_SECRET_PREVIOUS` | Previous HMAC key (for zero-downtime rotation) | During key rotation |
| `AIS_RISK_HMAC_KEY_ID` | Identifier for current key (e.g., `v1`, `v2`) | Optional (default: `v1`) |
| `AIS_API_KEY` | Bearer token for API auth | Live mode |
| `AIS_EXECUTION_MODE` | `paper` / `shadow` / `live` | Always (default: paper) |
| `AIS_ENABLE_LIVE_TRADING` | Safety gate for live orders | Live mode |
| `AIS_MCP_SERVER_URL` | Aster DEX MCP server endpoint | Shadow / Live mode |
| `ASTER_ACCOUNT_ID` | Aster DEX account identifier | Live mode |
| `AIS_BINANCE_MCP_URL` | Binance MCP server endpoint | When Binance enabled |
| `BINANCE_API_KEY` | Binance API key | When Binance enabled |
| `BINANCE_API_SECRET` | Binance API secret | When Binance enabled |
| `AIS_COINBASE_MCP_URL` | Coinbase MCP server endpoint | When Coinbase enabled |
| `COINBASE_API_KEY` | Coinbase API key | When Coinbase enabled |
| `COINBASE_API_SECRET` | Coinbase API secret | When Coinbase enabled |
| `AIS_BYBIT_MCP_URL` | Bybit MCP server endpoint | When Bybit enabled |
| `BYBIT_API_KEY` | Bybit API key | When Bybit enabled |
| `BYBIT_API_SECRET` | Bybit API secret | When Bybit enabled |
| `AIS_IB_MCP_URL` | Interactive Brokers MCP endpoint | When IB enabled |
| `IB_ACCOUNT_ID` | IB account ID | When IB enabled |
| `AIS_TV_WEBHOOK_SECRET` | TradingView webhook HMAC secret | When TV enabled |
| `AIS_TV_WEBHOOK_PORT` | TradingView webhook listener port | When TV enabled |
| `REDIS_URL` | Redis connection for control state | Always (default: redis://localhost:6379/0) |
| `AIS_SECRETS_FILE` | File-based secrets path (JSON) | Optional (alt secrets backend) |
| `AIS_SECRETS_DIR` | Directory-based secrets path | Optional (alt secrets backend) |
| `AIS_DB_PATH` | EventStore database path | Optional (default: data/ais_events.db) |
| `AIS_LOOP_METRICS_PORT` | Loop Prometheus metrics port | Optional (default: 9002) |
| `AIS_SLACK_WEBHOOK_URL` | Slack alert webhook | Optional (alert dispatch) |
| `AIS_ALERT_WEBHOOK_URL` | Generic alert webhook | Optional (alert dispatch) |
| `AIS_ALERTMANAGER_URL` | Alertmanager base URL | Optional (alert dispatch) |
| `AIS_PUSHGATEWAY_URL` | Prometheus Pushgateway URL | Optional (backtest metrics) |

## Exchange Provider Architecture

All exchange communication goes through `ExchangeProvider` (ABC in `exchange/provider.py`):

- **Paper**: `AsterExchangeProvider(MockMCPGateway())` — simulated fills
- **Shadow/Live**: `AsterExchangeProvider(HTTPMCPGateway(...))` — real exchange via MCP
- Provider auto-selected by execution mode; override via `bootstrap_from_config(gateway=...)`
- Each provider encapsulates ALL exchange-specific tool names (e.g., `mcp__aster__create_order`)
- `ExchangeRegistry` manages multiple providers; `SymbolRouter` maps symbols to exchanges

### Supported Exchanges

| Exchange | ID | Asset Classes | Symbol Format |
|----------|----|---------------|---------------|
| Aster DEX | `aster` | SPOT, FUTURES | `BTCUSDT` |
| Binance | `binance` | SPOT, FUTURES | `BTCUSDT` |
| Coinbase | `coinbase` | SPOT | `BTC-USD` |
| Bybit | `bybit` | SPOT, FUTURES, OPTIONS | `BTCUSDT` |
| Interactive Brokers | `ib` | STOCKS, OPTIONS, FUTURES, FOREX | `AAPL`, `BTCUSD` |

### CLI

```bash
python -m aiswarm --mode paper --exchange aster            # Single exchange
python -m aiswarm --mode paper --exchanges aster,binance   # Multi-exchange
python -m aiswarm --tradingview-port 8001                  # Enable TV webhooks
```

## Conventions

- Python 3.10+, type hints on all signatures
- Pydantic v2 for domain models (frozen=True)
- stdlib `logging` with custom `JsonFormatter` for structured logging
- SQLite EventStore for append-only audit trail
- YAML config in `config/` (base, risk, execution, mandates, portfolio, monitoring, exchanges, integrations)
- Tests in `tests/unit/` using pytest, 83% coverage minimum
