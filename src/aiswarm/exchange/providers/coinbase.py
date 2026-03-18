"""Coinbase exchange provider.

Encapsulates ALL mcp__coinbase__ tool name references. No other module in the
codebase should contain hardcoded Coinbase MCP tool names -- they all go through
this provider.

Coinbase specifics:
  - Symbol format: "BTC-USD" (dash-separated, USD quote)
  - Supports SPOT only (Coinbase International for FUTURES later)
  - Response keys differ from Aster: "product_id" vs "symbol", "size" vs "quantity"
  - Order book levels are dicts ({"price": ..., "size": ...}) not arrays
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aiswarm.exchange.provider import AssetClass, ExchangeProvider, Venue
from aiswarm.exchange.types import (
    AccountBalance,
    ExchangePosition,
    FundingRate,
    OHLCV,
    OrderBook,
    OrderBookLevel,
    Ticker,
    TradeRecord,
)
from aiswarm.execution.mcp_gateway import MCPGateway
from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)

# --- Coinbase MCP tool name constants ---

_TOOL_CREATE_ORDER = "mcp__coinbase__create_order"
_TOOL_CANCEL_ORDER = "mcp__coinbase__cancel_order"
_TOOL_CANCEL_ALL_ORDERS = "mcp__coinbase__cancel_all_orders"
_TOOL_GET_ORDER = "mcp__coinbase__get_order"
_TOOL_GET_MY_TRADES = "mcp__coinbase__get_my_trades"
_TOOL_GET_BALANCE = "mcp__coinbase__get_balance"
_TOOL_GET_KLINES = "mcp__coinbase__get_klines"
_TOOL_GET_TICKER = "mcp__coinbase__get_ticker"
_TOOL_GET_ORDER_BOOK = "mcp__coinbase__get_order_book"

# --- Symbol normalization ---

_QUOTE_ALIASES: dict[str, str] = {
    "USDT": "USD",
    "USDC": "USD",
}


def normalize_symbol(canonical: str) -> str:
    """Convert canonical symbol to Coinbase format.

    Examples:
        "BTC/USDT" -> "BTC-USD"
        "BTC/USD"  -> "BTC-USD"
        "ETH/USDT" -> "ETH-USD"
        "BTC-USD"  -> "BTC-USD"  (already normalized)
    """
    # Already in Coinbase format
    if "-" in canonical and "/" not in canonical:
        return canonical.upper()

    # Canonical "BASE/QUOTE" format
    if "/" in canonical:
        base, quote = canonical.split("/", 1)
        quote = _QUOTE_ALIASES.get(quote.upper(), quote.upper())
        return f"{base.upper()}-{quote}"

    # Fallback: try to detect concatenated format (e.g. "BTCUSDT")
    for suffix in ("USDT", "USDC", "USD"):
        if canonical.upper().endswith(suffix):
            base = canonical.upper()[: -len(suffix)]
            quote = _QUOTE_ALIASES.get(suffix, suffix)
            return f"{base}-{quote}"

    return canonical.upper()


def to_canonical_symbol(exchange_sym: str) -> str:
    """Convert Coinbase symbol to canonical format.

    Examples:
        "BTC-USD" -> "BTC/USD"
        "ETH-USD" -> "ETH/USD"
    """
    if "-" in exchange_sym:
        base, quote = exchange_sym.split("-", 1)
        return f"{base.upper()}/{quote.upper()}"
    return exchange_sym


# --- Coinbase response parsers ---


def parse_ohlcv(raw: dict[str, Any], symbol: str) -> OHLCV:
    """Parse a single kline entry from Coinbase response.

    Coinbase format: {"start": epoch, "open": "50000", "high": "51000", ...}
    """
    ts = raw.get("start") or raw.get("timestamp") or 0
    ts_float = float(ts)
    if ts_float > 1e12:
        ts_float = ts_float / 1000  # ms to seconds
    return OHLCV(
        timestamp=datetime.fromtimestamp(ts_float, tz=timezone.utc),
        open=float(raw.get("open", 0)),
        high=float(raw.get("high", 0)),
        low=float(raw.get("low", 0)),
        close=float(raw.get("close", 0)),
        volume=float(raw.get("volume", 0)),
        symbol=to_canonical_symbol(symbol),
    )


def parse_ticker(raw: dict[str, Any]) -> Ticker:
    """Parse Coinbase ticker response.

    Coinbase format: {"product_id": "BTC-USD", "price": "50000", "volume_24h": "1000", ...}
    """
    product_id = raw.get("product_id", "")
    return Ticker(
        symbol=to_canonical_symbol(product_id),
        last_price=float(raw.get("price", 0)),
        high_24h=float(raw.get("high_24h", 0)),
        low_24h=float(raw.get("low_24h", 0)),
        volume_24h=float(raw.get("volume_24h", 0)),
        price_change_pct=float(raw.get("price_change_pct", 0)),
        timestamp=datetime.now(timezone.utc),
    )


def parse_order_book(raw: dict[str, Any], symbol: str) -> OrderBook:
    """Parse Coinbase order book response.

    Coinbase format: {"bids": [{"price": "50000", "size": "1.0"}, ...], "asks": [...]}
    Note: Coinbase uses dicts with "price"/"size" keys, not arrays.
    """
    bids = tuple(
        OrderBookLevel(price=float(b["price"]), quantity=float(b["size"]))
        for b in raw.get("bids", [])
    )
    asks = tuple(
        OrderBookLevel(price=float(a["price"]), quantity=float(a["size"]))
        for a in raw.get("asks", [])
    )
    return OrderBook(
        symbol=to_canonical_symbol(symbol),
        bids=bids,
        asks=asks,
        timestamp=datetime.now(timezone.utc),
    )


def parse_balance(raw: dict[str, Any]) -> AccountBalance:
    """Parse Coinbase balance response.

    Coinbase format: {"currency": "USD", "balance": "100000", "available": "80000"}
    """
    return AccountBalance(
        total_balance=float(raw.get("balance", 0)),
        available_balance=float(raw.get("available", 0)),
        unrealized_pnl=0.0,  # Spot only, no unrealized PnL
        margin_balance=0.0,  # Spot only, no margin
        asset=raw.get("currency", "USD"),
    )


def parse_trade(raw: dict[str, Any]) -> TradeRecord:
    """Parse a single Coinbase trade/fill entry.

    Coinbase format: {"trade_id": "T1", "product_id": "BTC-USD", "side": "buy",
                      "price": "50000", "size": "0.1", "fee": "5"}
    """
    ts = raw.get("time") or raw.get("timestamp") or 0
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            dt = datetime.now(timezone.utc)
    elif isinstance(ts, (int, float)):
        ts_float = float(ts)
        if ts_float > 1e12:
            ts_float = ts_float / 1000
        dt = datetime.fromtimestamp(ts_float, tz=timezone.utc)
    else:
        dt = datetime.now(timezone.utc)

    product_id = raw.get("product_id", "")
    return TradeRecord(
        trade_id=str(raw.get("trade_id", "")),
        symbol=to_canonical_symbol(product_id),
        side=raw.get("side", "").upper(),
        price=float(raw.get("price", 0)),
        quantity=float(raw.get("size", 0)),
        commission=float(raw.get("fee", 0)),
        commission_asset=raw.get("fee_currency", "USD"),
        realized_pnl=0.0,  # Spot only
        timestamp=dt,
        order_id=str(raw.get("order_id", "")),
    )


def _normalize_order_response(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Coinbase order response to include 'orderId' key.

    Coinbase returns "id" instead of "orderId" and "product_id" instead of "symbol".
    """
    result = dict(raw)
    if "orderId" not in result and "id" in result:
        result["orderId"] = result["id"]
    if "symbol" not in result and "product_id" in result:
        result["symbol"] = result["product_id"]
    if "quantity" not in result and "size" in result:
        result["quantity"] = result["size"]
    return result


# --- Provider class ---


class CoinbaseExchangeProvider(ExchangeProvider):
    """Coinbase exchange provider.

    Wraps the MCPGateway into a clean ExchangeProvider interface.
    All Coinbase-specific MCP tool names and response parsing are
    encapsulated here.

    Supports SPOT only. Futures support (via Coinbase International)
    will be added later.
    """

    def __init__(self, gateway: MCPGateway) -> None:
        self.gateway = gateway

    @property
    def exchange_id(self) -> str:
        return "coinbase"

    @property
    def supported_asset_classes(self) -> AssetClass:
        return AssetClass.SPOT

    # --- Symbol normalization ---

    def normalize_symbol(self, canonical: str) -> str:
        return normalize_symbol(canonical)

    def to_canonical_symbol(self, exchange_sym: str) -> str:
        return to_canonical_symbol(exchange_sym)

    # --- Market Data ---

    def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
    ) -> list[OHLCV]:
        cb_symbol = self.normalize_symbol(symbol)
        response = self._call_safe(
            _TOOL_GET_KLINES,
            {"product_id": cb_symbol, "granularity": interval, "limit": limit},
        )
        if response is None:
            return []
        data: list[dict[str, Any]] = []
        if isinstance(response, list):
            data = response
        elif isinstance(response, dict) and "candles" in response:
            data = response["candles"]
        elif isinstance(response, dict):
            data = [response]
        return [parse_ohlcv(entry, cb_symbol) for entry in data]

    def get_ticker(self, symbol: str) -> Ticker | None:
        cb_symbol = self.normalize_symbol(symbol)
        response = self._call_safe(_TOOL_GET_TICKER, {"product_id": cb_symbol})
        if response is None:
            return None
        if isinstance(response, dict):
            data = response.get("data", response)
            return parse_ticker(data)
        return None

    def get_order_book(self, symbol: str) -> OrderBook | None:
        cb_symbol = self.normalize_symbol(symbol)
        response = self._call_safe(_TOOL_GET_ORDER_BOOK, {"product_id": cb_symbol})
        if response is None:
            return None
        if isinstance(response, dict):
            data = response.get("data", response)
            return parse_order_book(data, cb_symbol)
        return None

    def get_funding_rate(self, symbol: str) -> FundingRate | None:
        """Coinbase spot does not have funding rates."""
        return None

    # --- Account ---

    def get_balance(self) -> AccountBalance | None:
        response = self._call_safe(_TOOL_GET_BALANCE, {})
        if response is None:
            return None
        if isinstance(response, dict):
            data = response.get("data", response)
            if isinstance(data, list) and data:
                return parse_balance(data[0])
            return parse_balance(data)
        return None

    def get_positions(self) -> list[ExchangePosition]:
        """Coinbase spot has no positions concept. Returns empty list."""
        return []

    # --- Trading ---

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "MARKET",
        price: float | None = None,
        venue: str = Venue.SPOT,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if venue != Venue.SPOT:
            raise NotImplementedError(f"coinbase provider only supports spot venue, got '{venue}'")
        params: dict[str, Any] = {
            "product_id": self.normalize_symbol(symbol),
            "side": side.lower(),
            "size": str(quantity),
            "order_type": order_type.lower(),
        }
        if price is not None:
            params["price"] = str(price)
            params["time_in_force"] = kwargs.get("time_in_force", "GTC")
        params.update({k: v for k, v in kwargs.items() if k != "time_in_force"})

        response = self.gateway.call_tool(_TOOL_CREATE_ORDER, params)
        return _normalize_order_response(response)

    def cancel_order(
        self,
        symbol: str,
        order_id: str,
        venue: str = Venue.SPOT,
    ) -> dict[str, Any]:
        params = {
            "product_id": self.normalize_symbol(symbol),
            "order_id": order_id,
        }
        return self.gateway.call_tool(_TOOL_CANCEL_ORDER, params)

    def cancel_all_orders(
        self,
        symbol: str,
        venue: str = Venue.SPOT,
    ) -> dict[str, Any]:
        params = {
            "product_id": self.normalize_symbol(symbol),
        }
        return self.gateway.call_tool(_TOOL_CANCEL_ALL_ORDERS, params)

    def get_order_status(
        self,
        symbol: str,
        order_id: str,
        venue: str = Venue.SPOT,
    ) -> dict[str, Any]:
        params = {
            "product_id": self.normalize_symbol(symbol),
            "order_id": order_id,
        }
        response = self.gateway.call_tool(_TOOL_GET_ORDER, params)
        return _normalize_order_response(response)

    def get_my_trades(
        self,
        symbol: str,
        venue: str = Venue.SPOT,
    ) -> list[TradeRecord]:
        cb_symbol = self.normalize_symbol(symbol)
        response = self._call_safe(
            _TOOL_GET_MY_TRADES,
            {"product_id": cb_symbol},
        )
        if response is None:
            return []
        data: list[dict[str, Any]] = []
        if isinstance(response, dict):
            raw = response.get("fills", response.get("data", []))
            data = raw if isinstance(raw, list) else []
            if isinstance(data, dict):
                data = [data]
        elif isinstance(response, list):
            data = response
        return [parse_trade(t) for t in data]

    # --- Leverage/Margin (not supported for spot) ---

    def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        raise NotImplementedError("coinbase does not support set_leverage (spot only)")

    def set_margin_mode(self, symbol: str, mode: str) -> dict[str, Any]:
        raise NotImplementedError("coinbase does not support set_margin_mode (spot only)")

    # --- Internal ---

    def _call_safe(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Call a tool, returning None on error."""
        try:
            return self.gateway.call_tool(tool_name, params)
        except Exception as e:
            logger.warning(
                "Coinbase MCP call failed",
                extra={"extra_json": {"tool": tool_name, "error": str(e)}},
            )
            return None
