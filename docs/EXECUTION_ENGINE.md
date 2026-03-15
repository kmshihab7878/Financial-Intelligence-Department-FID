# Execution Engine

## Components

### Order Management System (`execution/oms.py`)

The OMS is the final gate before order submission. It verifies the HMAC-signed risk approval token on every order:

1. Checks token is present
2. Verifies HMAC signature matches (using `AIS_RISK_HMAC_SECRET`)
3. Checks token is not expired (5-minute TTL)
4. Transitions order status from `APPROVED` to `SUBMITTED`

Orders without valid tokens are rejected with `ValueError`.

### Aster DEX Executor (`execution/aster_executor.py`)

Adapter for Aster DEX exchange. Does NOT make MCP calls directly -- prepares parameters as structured dicts for the caller to invoke via MCP.

**Execution Modes**:

| Mode | Behavior |
|------|----------|
| `paper` | Simulates fills using current price. No MCP calls. |
| `shadow` | Fetches real data, simulates fills against real prices. No order submission. |
| `live` | Submits real orders via MCP. Requires `AIS_ENABLE_LIVE_TRADING=true` + valid account. |

**Order Preparation**:
- `prepare_futures_order(order)` -- params for `mcp__aster__create_order`
- `prepare_spot_order(order)` -- params for `mcp__aster__create_spot_order`
- Both verify risk approval tokens before preparing

**Cancellation**:
- `prepare_cancel_order(symbol, order_id, venue)` -- single order cancel
- `prepare_cancel_all(symbol, venue)` -- cancel all orders for a symbol
- `prepare_emergency_cancel_all(symbols)` -- cancel all across all symbols and venues (kill switch)

**Leverage/Margin Control**:
- `prepare_set_leverage(symbol, leverage)` -- enforce leverage ceiling
- `prepare_set_margin_mode(symbol, mode)` -- ISOLATED recommended to limit blast radius

**Paper Trading**:
- `simulate_paper_fill(order, current_price)` -- returns `ExecutionResult` with simulated fill
- `paper_fills` property exposes fill history

## Order Flow

```
Signal
  -> PortfolioAllocator.order_from_signal()
    -> Order (PENDING)
      -> RiskEngine.validate()
        -> Order (APPROVED, with HMAC token)
          -> OMS.submit()
            -> Order (SUBMITTED)
              -> AsterExecutor.prepare_futures_order()
                -> MCP call (live) or simulate_paper_fill (paper)
```

## Safety Gates

1. **Risk token**: HMAC-SHA256 signed, 5-min TTL, verified by both OMS and executor
2. **Live mode env var**: `AIS_ENABLE_LIVE_TRADING=true` must be explicitly set
3. **Account ID**: `ASTER_ACCOUNT_ID` required for live mode
4. **Leverage enforcement**: Must call `set_leverage` before first order
5. **Margin mode**: Must call `set_margin_mode` (ISOLATED recommended)
