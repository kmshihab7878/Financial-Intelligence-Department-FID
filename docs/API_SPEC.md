# API Specification

## Overview

AIS exposes a FastAPI application (`aiswarm.api.app`) at version 2.0.0.

**Authentication**: All control and report endpoints require Bearer token authentication via the `AIS_API_KEY` environment variable. Health and metrics endpoints are public.

## Endpoints

### Public

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | System health check. Returns `{"status": "ok"}` plus component health. |
| `GET` | `/metrics` | Prometheus-format metrics. |

### Control (Authenticated)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/control/mode` | Returns default execution mode (`{"default_mode": "paper"}`). |
| `GET` | `/control/status` | Returns system state: `running`, `paused`, or `killed`. |
| `POST` | `/control/pause` | Pause the coordinator loop. Body: `{"reason": "string"}`. |
| `POST` | `/control/resume` | Resume after pause. Refused if in `killed` state. |
| `POST` | `/control/kill-switch` | Emergency stop. Cancels all orders. Requires manual reset. Body: `{"reason": "string"}`. |
| `POST` | `/control/cancel-all` | Prepare cancel-all-orders MCP instructions. Body: `{"symbols": ["BTCUSDT"]}` or null for all whitelisted. |
| `POST` | `/control/deleverage` | Prepare reduce-only order for position reduction. Body: `{"symbol": "BTCUSDT", "reduce_pct": 1.0}`. |

### Reports (Authenticated)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/reports/decisions` | Recent decision log entries. |

## Authentication

Include the API key as a Bearer token:

```
Authorization: Bearer <AIS_API_KEY>
```

Set `AIS_API_KEY` in your `.env` file. Generate with: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## System State Machine

```
RUNNING --[POST /control/pause]--> PAUSED
PAUSED  --[POST /control/resume]--> RUNNING
RUNNING --[POST /control/kill-switch]--> KILLED
PAUSED  --[POST /control/kill-switch]--> KILLED
KILLED  -- (manual intervention required to restart)
```

## Kill Switch Response

The kill switch returns MCP cancel instructions for all whitelisted symbols:

```json
{
  "action": "killed",
  "reason": "manual kill switch",
  "cancel_instructions": [
    {"tool": "mcp__aster__cancel_all_orders", "symbol": "BTCUSDT"},
    {"tool": "mcp__aster__cancel_spot_all_orders", "symbol": "BTCUSDT"}
  ]
}
```

The operator must execute these MCP calls to cancel open orders on Aster DEX.

## Error Responses

All errors follow the FastAPI default format:

```json
{
  "detail": "Not authenticated"
}
```

Standard HTTP status codes: 401 (unauthorized), 422 (validation error), 500 (internal error).
