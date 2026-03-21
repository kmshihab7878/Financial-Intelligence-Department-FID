# Quick Start

Get AIS running in paper trading mode in under 5 minutes.

## 1. Install

```bash
git clone https://github.com/kmshihab7878/Autonomous-Investment-Swarm.git
cd Autonomous-Investment-Swarm
pip install -e ".[dev]"
```

## 2. Configure

```bash
cp .env.example .env
```

At minimum, set the HMAC secret:

```bash
export AIS_RISK_HMAC_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
```

## 3. Start Redis

```bash
# Option 1: Local Redis
redis-server &

# Option 2: Docker
docker run -d -p 6379:6379 redis:7-alpine
```

## 4. Run Paper Trading

```bash
python -m aiswarm --mode paper
```

You should see structured JSON output:

```json
{"event": "session_started", "mode": "paper", "strategies": ["momentum_ma_crossover", "funding_rate_contrarian"]}
{"event": "cycle_start", "cycle": 1, "timestamp": "2026-01-15T10:00:00Z"}
{"event": "signal_generated", "agent": "momentum", "symbol": "BTCUSDT", "direction": 1, "confidence": 0.72}
{"event": "risk_approved", "symbol": "BTCUSDT", "size": 0.001, "token": "hmac:a3f2..."}
{"event": "order_submitted", "symbol": "BTCUSDT", "side": "BUY", "qty": 0.001, "mode": "paper"}
{"event": "cycle_end", "cycle": 1, "duration_ms": 245}
```

## 5. Start the API

In a separate terminal:

```bash
uvicorn aiswarm.api.app:app --app-dir src --reload
```

Check the system:

```bash
# Health check (no auth required)
curl http://localhost:8000/health

# System status (requires API key)
export AIS_API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
curl -H "Authorization: Bearer $AIS_API_KEY" http://localhost:8000/control/status
```

## 6. Check Metrics

With the API running, Prometheus metrics are available at:

```bash
curl http://localhost:8000/metrics
```

## What Just Happened?

Each 60-second cycle:

1. **Strategy agents** analyzed market data and generated `Signal` objects
2. **Weighted arbitration** selected the best signal
3. **Portfolio allocator** sized the order based on NAV and confidence
4. **Risk engine** validated the order against all guards (drawdown, leverage, liquidity, exposure)
5. **Risk engine** signed the approved order with an HMAC token
6. **OMS** verified the token and submitted to the paper trading simulator
7. **Event store** recorded the decision for audit trail

## Next Steps

- [Configuration](configuration.md) — Customize risk limits, strategies, and exchanges
- [Strategy Development](../guides/strategy-development.md) — Build your own strategy agent
- [Deployment](../guides/deployment.md) — Run the full stack with Docker Compose
- [Architecture](../architecture/overview.md) — Understand the system design
