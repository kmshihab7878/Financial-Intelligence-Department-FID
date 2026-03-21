# Multi-Exchange Setup

AIS supports routing orders across multiple exchanges through a unified abstraction layer.

## Supported Exchanges

| Exchange | Spot | Futures | Options | Symbol Format |
|----------|:----:|:-------:|:-------:|---------------|
| Aster DEX | x | x | | `BTCUSDT` |
| Binance | x | x | | `BTCUSDT` |
| Coinbase | x | | | `BTC-USD` |
| Bybit | x | x | x | `BTCUSDT` |
| Interactive Brokers | x | x | x | `AAPL`, `BTCUSD` |

## Configuration

### 1. Enable Exchanges

Edit `config/exchanges.yaml`:

```yaml
exchanges:
  aster:
    enabled: true
    asset_classes: [spot, futures]
    symbols: [BTCUSDT, ETHUSDT]

  binance:
    enabled: true
    asset_classes: [spot, futures]
    symbols: [SOLUSDT, AVAXUSDT]

  coinbase:
    enabled: false
```

### 2. Set Credentials

Add exchange-specific environment variables to `.env`:

```bash
# Binance
AIS_BINANCE_MCP_URL=http://localhost:8002
BINANCE_API_KEY=your-api-key
BINANCE_API_SECRET=your-api-secret

# Bybit
AIS_BYBIT_MCP_URL=http://localhost:8003
BYBIT_API_KEY=your-api-key
BYBIT_API_SECRET=your-api-secret
```

### 3. Run with Multiple Exchanges

```bash
python -m aiswarm --mode paper --exchanges aster,binance
```

## Symbol Routing

The `SymbolRouter` maps each symbol to its designated exchange based on `exchanges.yaml`. When a strategy generates a signal for `SOLUSDT`, the router directs the order to Binance (if configured).

If a symbol appears in multiple exchange configs, the first match wins.

## Exchange-Specific Notes

### Aster DEX
- Default exchange when no others are configured
- All MCP tool references are encapsulated in `AsterExchangeProvider`
- Supports both spot and futures

### Binance
- Requires API key and secret for authenticated endpoints
- Spot and futures use different base URLs
- Rate limits apply — the built-in rate limiter handles this

### Coinbase
- Spot only — no futures or margin trading
- Uses `BTC-USD` symbol format (hyphenated)
- Requires Coinbase API key with trading permissions

### Bybit
- Supports spot, futures, and options via the v5 API
- Uses `BTCUSDT` format for all asset classes

### Interactive Brokers
- Supports stocks, options, futures, and forex
- Uses standard ticker symbols (`AAPL`, `BTCUSD`)
- Requires IB Gateway or TWS running locally

## Architecture

See [Exchange Layer](../architecture/exchange-layer.md) for the technical architecture, including how to add new exchanges.
