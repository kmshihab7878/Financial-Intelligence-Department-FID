# Data Model

## Core Types

All models use Pydantic with `frozen=True` for immutability. Located in `src/aiswarm/types/`.

### Market Types (`types/market.py`)

**Signal**: Output of an agent's analysis.

| Field | Type | Constraints |
|-------|------|-------------|
| `signal_id` | `str` | Unique identifier |
| `agent_id` | `str` | Originating agent |
| `symbol` | `str` | Instrument symbol |
| `strategy` | `str` | Strategy name |
| `thesis` | `str` | min_length=5 |
| `direction` | `int` | -1, 0, or 1 |
| `confidence` | `float` | 0.0 to 1.0 |
| `expected_return` | `float` | Expected return |
| `horizon_minutes` | `int` | > 0 |
| `liquidity_score` | `float` | 0.0 to 1.0 |
| `regime` | `MarketRegime` | risk_on, risk_off, transition, stressed |

**MarketRegime**: Enum -- `RISK_ON`, `RISK_OFF`, `TRANSITION`, `STRESSED`.

### Order Types (`types/orders.py`)

**Order**: Represents a trade intent.

| Field | Type | Constraints |
|-------|------|-------------|
| `order_id` | `str` | Unique identifier |
| `signal_id` | `str` | Source signal |
| `symbol` | `str` | Instrument |
| `side` | `Side` | BUY or SELL |
| `quantity` | `float` | > 0 |
| `limit_price` | `float \| None` | > 0 if set |
| `notional` | `float` | > 0 |
| `strategy` | `str` | Strategy name |
| `thesis` | `str` | min_length=5 |
| `risk_approval_token` | `str \| None` | HMAC-signed token |
| `status` | `OrderStatus` | pending -> approved -> submitted -> filled |

**OrderStatus**: `PENDING` -> `APPROVED` -> `SUBMITTED` -> `FILLED` / `REJECTED` / `CANCELLED`.

### Portfolio Types (`types/portfolio.py`)

**Position**: `symbol`, `quantity`, `avg_price`, `market_price`, `strategy`. Computed: `market_value`.

**PortfolioSnapshot**: `timestamp`, `nav`, `cash`, `gross_exposure`, `net_exposure`, `positions`.

### Risk Types (`types/risk.py`)

**RiskEvent**: `event_id`, `severity` (INFO/WARNING/CRITICAL), `rule`, `message`, `symbol`, `strategy`.

### Decision Types (`types/decisions.py`)

**DecisionLog**: Records arbitration and risk outcomes per coordinator cycle. See `DECISION_LOG_SCHEMA.md`.

## Aster DEX Canonical Types (`data/providers/aster.py`)

Parsed from raw MCP responses:

| Type | Fields |
|------|--------|
| `OHLCV` | open_time, open, high, low, close, volume, close_time |
| `Ticker` | symbol, last_price, price_change_pct, high_24h, low_24h, volume_24h, quote_volume_24h |
| `OrderBook` | symbol, bids, asks. Properties: `spread`, `spread_pct`, `bid_depth`, `ask_depth` |
| `FundingRate` | symbol, rate, mark_price, next_funding_time |
| `AccountBalance` | asset, total_balance, available_balance, unrealized_pnl |
| `ExchangePosition` | symbol, side, quantity, entry_price, mark_price, unrealized_pnl, leverage, margin_mode |
| `TradeRecord` | trade_id, symbol, side, price, quantity, commission, timestamp |
| `ExchangeInfo` | symbol, base_asset, quote_asset, price_precision, quantity_precision, min_quantity, tick_size |
| `LeverageBracket` | bracket, initial_leverage, notional_cap, maintenance_margin_rate |

## Event Store (`data/event_store.py`)

SQLite-backed append-only store with two tables:

- **events**: `id`, `event_type`, `timestamp`, `payload` (JSON), `source`
- **checkpoints**: `id`, `checkpoint_type`, `timestamp`, `payload` (JSON)

Event types: `decision`, `order`, `risk_event`, `fill`, `reconciliation`.
Checkpoint types: `portfolio`, `shared_memory`.
