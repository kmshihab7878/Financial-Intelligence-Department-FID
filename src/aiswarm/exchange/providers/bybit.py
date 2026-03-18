"""Bybit exchange provider (v5 unified API).

Encapsulates ALL mcp__bybit__ tool name references. No other module in the
codebase should contain hardcoded Bybit MCP tool names -- they all go through
this provider.

Bybit v5 unified API wraps every response in ``{"retCode": 0, "result": {...}}``.
This provider transparently unwraps the ``result`` field and parses it into
canonical types. If ``retCode`` is non-zero the provider treats the call as
failed and returns a safe default (None / empty list).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from aiswarm.exchange.provider import AssetClass, ExchangeProvider, Venue
from aiswarm.exchange.types import (
    AccountBalance,
    ExchangePosition,
    FundingRate,
    IncomeRecord,
    OHLCV,
    OrderBook,
    OrderBookLevel,
    Ticker,
    TradeRecord,
)
from aiswarm.execution.mcp_gateway import MCPGateway
from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Bybit MCP tool name constants
# ---------------------------------------------------------------------------
# Bybit v5 unified API uses a single set of endpoints; the ``category``
# parameter selects the venue (linear, inverse, spot, option).

_TOOL_CREATE_ORDER = "mcp__bybit__create_order"
_TOOL_CANCEL_ORDER = "mcp__bybit__cancel_order"
_TOOL_CANCEL_ALL_ORDERS = "mcp__bybit__cancel_all_orders"
_TOOL_GET_ORDER = "mcp__bybit__get_order"
_TOOL_GET_OPEN_ORDERS = "mcp__bybit__get_open_orders"
_TOOL_GET_MY_TRADES = "mcp__bybit__get_my_trades"
_TOOL_GET_BALANCE = "mcp__bybit__get_balance"
_TOOL_GET_POSITIONS = "mcp__bybit__get_positions"
_TOOL_GET_INCOME = "mcp__bybit__get_income"
_TOOL_GET_KLINES = "mcp__bybit__get_klines"
_TOOL_GET_FUNDING_RATE = "mcp__bybit__get_funding_rate"
_TOOL_GET_TICKER = "mcp__bybit__get_ticker"
_TOOL_GET_ORDER_BOOK = "mcp__bybit__get_order_book"
_TOOL_SET_LEVERAGE = "mcp__bybit__set_leverage"
_TOOL_SET_MARGIN_MODE = "mcp__bybit__set_margin_mode"

# ---------------------------------------------------------------------------
# Symbol helpers
# ---------------------------------------------------------------------------

# Regex to detect canonical "BASE/QUOTE" format.
_CANONICAL_RE = re.compile(r"^([A-Z0-9]+)/([A-Z0-9]+)$")

# Known quote assets ordered longest-first so BUSD matches before USD.
_QUOTE_ASSETS = ("USDT", "USDC", "BUSD", "USD", "BTC", "ETH")


def _normalize_symbol(canonical: str) -> str:
    """Convert canonical ``BTC/USDT`` to Bybit format ``BTCUSDT``."""
    m = _CANONICAL_RE.match(canonical)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    # Already in exchange format -- return as-is.
    return canonical


def _to_canonical_symbol(exchange_sym: str) -> str:
    """Convert Bybit ``BTCUSDT`` to canonical ``BTC/USDT``."""
    if "/" in exchange_sym:
        return exchange_sym  # already canonical
    for quote in _QUOTE_ASSETS:
        if exchange_sym.endswith(quote):
            base = exchange_sym[: -len(quote)]
            if base:
                return f"{base}/{quote}"
    # Inverse contracts (e.g. "BTCUSD") -- treat USD as quote.
    return exchange_sym


def _venue_to_category(venue: str) -> str:
    """Map the generic venue string to Bybit's ``category`` parameter."""
    if venue == Venue.SPOT:
        return "spot"
    if venue == Venue.FUTURES:
        return "linear"
    return venue  # allow pass-through of "inverse", "option"


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------


def _unwrap_result(response: dict[str, Any]) -> dict[str, Any] | list[Any] | None:
    """Unwrap Bybit v5 response envelope.

    Bybit wraps every v5 response as ``{"retCode": 0, "result": {...}}``.
    Returns the inner ``result`` if ``retCode`` is 0, otherwise ``None``.
    """
    ret_code = response.get("retCode")
    if ret_code is not None and ret_code != 0:
        logger.warning(
            "Bybit API returned non-zero retCode",
            extra={
                "extra_json": {
                    "retCode": ret_code,
                    "retMsg": response.get("retMsg", ""),
                }
            },
        )
        return None
    result: dict[str, Any] | list[Any] | None = response.get("result", response)
    return result


def _ts_to_datetime(ts: int | str) -> datetime:
    """Convert a millisecond timestamp (int or string) to a UTC datetime."""
    return datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc)


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert a value to float, returning *default* on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Bybit Exchange Provider
# ---------------------------------------------------------------------------


class BybitExchangeProvider(ExchangeProvider):
    """Bybit exchange provider (v5 unified API).

    Wraps the MCPGateway into a clean ExchangeProvider interface. All Bybit-
    specific MCP tool names and v5 response parsing are encapsulated here.
    """

    def __init__(self, gateway: MCPGateway) -> None:
        self.gateway = gateway

    # --- Properties ----------------------------------------------------------

    @property
    def exchange_id(self) -> str:
        return "bybit"

    @property
    def supported_asset_classes(self) -> AssetClass:
        return AssetClass.SPOT | AssetClass.FUTURES | AssetClass.OPTIONS

    # --- Symbol normalization ------------------------------------------------

    def normalize_symbol(self, canonical: str) -> str:
        return _normalize_symbol(canonical)

    def to_canonical_symbol(self, exchange_sym: str) -> str:
        return _to_canonical_symbol(exchange_sym)

    # --- Market Data ---------------------------------------------------------

    def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
    ) -> list[OHLCV]:
        response = self._call_safe(
            _TOOL_GET_KLINES,
            {
                "category": "linear",
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            },
        )
        if response is None:
            return []
        return self._parse_klines(response, symbol)

    def get_ticker(self, symbol: str) -> Ticker | None:
        response = self._call_safe(
            _TOOL_GET_TICKER,
            {"category": "linear", "symbol": symbol},
        )
        if response is None:
            return None
        return self._parse_ticker(response)

    def get_order_book(self, symbol: str) -> OrderBook | None:
        response = self._call_safe(
            _TOOL_GET_ORDER_BOOK,
            {"category": "linear", "symbol": symbol},
        )
        if response is None:
            return None
        return self._parse_order_book(response, symbol)

    def get_funding_rate(self, symbol: str) -> FundingRate | None:
        response = self._call_safe(
            _TOOL_GET_FUNDING_RATE,
            {"category": "linear", "symbol": symbol},
        )
        if response is None:
            return None
        return self._parse_funding_rate(response)

    # --- Account -------------------------------------------------------------

    def get_balance(self) -> AccountBalance | None:
        response = self._call_safe(
            _TOOL_GET_BALANCE,
            {"accountType": "UNIFIED"},
        )
        if response is None:
            return None
        return self._parse_balance(response)

    def get_positions(self) -> list[ExchangePosition]:
        response = self._call_safe(
            _TOOL_GET_POSITIONS,
            {"category": "linear"},
        )
        if response is None:
            return []
        return self._parse_positions(response)

    def get_income(self) -> list[IncomeRecord]:
        response = self._call_safe(
            _TOOL_GET_INCOME,
            {"category": "linear"},
        )
        if response is None:
            return []
        return self._parse_income(response)

    # --- Trading -------------------------------------------------------------

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "MARKET",
        price: float | None = None,
        venue: str = "futures",
        **kwargs: Any,
    ) -> dict[str, Any]:
        category = _venue_to_category(venue)
        params: dict[str, Any] = {
            "category": category,
            "symbol": self.normalize_symbol(symbol),
            "side": side,
            "orderType": order_type,
            "qty": str(quantity),
        }
        if price is not None:
            params["price"] = str(price)
            params["timeInForce"] = kwargs.get("time_in_force", "GTC")
        params.update({k: v for k, v in kwargs.items() if k != "time_in_force"})

        raw = self.gateway.call_tool(_TOOL_CREATE_ORDER, params)
        return self._unwrap_order_response(raw)

    def cancel_order(
        self,
        symbol: str,
        order_id: str,
        venue: str = "futures",
    ) -> dict[str, Any]:
        category = _venue_to_category(venue)
        params = {
            "category": category,
            "symbol": self.normalize_symbol(symbol),
            "orderId": order_id,
        }
        raw = self.gateway.call_tool(_TOOL_CANCEL_ORDER, params)
        return self._unwrap_order_response(raw)

    def cancel_all_orders(
        self,
        symbol: str,
        venue: str = "futures",
    ) -> dict[str, Any]:
        category = _venue_to_category(venue)
        params = {
            "category": category,
            "symbol": self.normalize_symbol(symbol),
        }
        raw = self.gateway.call_tool(_TOOL_CANCEL_ALL_ORDERS, params)
        return self._unwrap_order_response(raw)

    def get_order_status(
        self,
        symbol: str,
        order_id: str,
        venue: str = "futures",
    ) -> dict[str, Any]:
        category = _venue_to_category(venue)
        params = {
            "category": category,
            "symbol": self.normalize_symbol(symbol),
            "orderId": order_id,
        }
        raw = self.gateway.call_tool(_TOOL_GET_ORDER, params)
        return self._unwrap_order_response(raw)

    def get_my_trades(
        self,
        symbol: str,
        venue: str = "futures",
    ) -> list[TradeRecord]:
        category = _venue_to_category(venue)
        response = self._call_safe(
            _TOOL_GET_MY_TRADES,
            {"category": category, "symbol": symbol},
        )
        if response is None:
            return []
        return self._parse_trades(response)

    # --- Leverage / Margin ---------------------------------------------------

    def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        params = {
            "category": "linear",
            "symbol": self.normalize_symbol(symbol),
            "buyLeverage": str(leverage),
            "sellLeverage": str(leverage),
        }
        raw = self.gateway.call_tool(_TOOL_SET_LEVERAGE, params)
        return self._unwrap_order_response(raw)

    def set_margin_mode(self, symbol: str, mode: str) -> dict[str, Any]:
        params = {
            "category": "linear",
            "symbol": self.normalize_symbol(symbol),
            "tradeMode": _margin_mode_to_bybit(mode),
        }
        raw = self.gateway.call_tool(_TOOL_SET_MARGIN_MODE, params)
        return self._unwrap_order_response(raw)

    # -----------------------------------------------------------------------
    # Internal: safe call + v5 response parsing
    # -----------------------------------------------------------------------

    def _call_safe(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Call a tool, unwrap the v5 envelope, return ``None`` on error."""
        try:
            raw = self.gateway.call_tool(tool_name, params)
        except Exception as e:
            logger.warning(
                "Bybit MCP call failed",
                extra={"extra_json": {"tool": tool_name, "error": str(e)}},
            )
            return None
        result = _unwrap_result(raw)
        if result is None:
            return None
        # Bybit sometimes returns the result directly as a dict; sometimes
        # the raw response *is* the result (MockMCPGateway). Handle both.
        if isinstance(result, dict):
            return result
        return raw

    def _unwrap_order_response(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Unwrap a Bybit v5 order response and normalise the key to ``orderId``."""
        result = _unwrap_result(raw)
        if isinstance(result, dict):
            out = dict(result)
        else:
            out = dict(raw)
        # Bybit returns "orderId" already, but just in case an older
        # version or mock returns "orderID" (capital D), normalise it.
        if "orderId" not in out and "orderID" in out:
            out["orderId"] = out.pop("orderID")
        return out

    # -----------------------------------------------------------------------
    # Parsers: Bybit v5 -> canonical types
    # -----------------------------------------------------------------------

    def _parse_klines(self, data: dict[str, Any], symbol: str) -> list[OHLCV]:
        """Parse Bybit v5 kline response.

        Bybit returns klines as arrays of strings inside ``result.list``:
        ``[["timestamp", "open", "high", "low", "close", "volume", "turnover"], ...]``
        """
        raw_list: list[list[str]] = data.get("list", [])
        klines: list[OHLCV] = []
        canonical = self.to_canonical_symbol(symbol)
        for row in raw_list:
            if len(row) < 6:
                continue
            klines.append(
                OHLCV(
                    timestamp=_ts_to_datetime(row[0]),
                    open=_safe_float(row[1]),
                    high=_safe_float(row[2]),
                    low=_safe_float(row[3]),
                    close=_safe_float(row[4]),
                    volume=_safe_float(row[5]),
                    symbol=canonical,
                )
            )
        return klines

    def _parse_ticker(self, data: dict[str, Any]) -> Ticker | None:
        """Parse Bybit v5 ticker response.

        ``result.list`` contains one or more ticker dicts.
        """
        items: list[dict[str, Any]] = data.get("list", [])
        if not items:
            return None
        t = items[0]
        return Ticker(
            symbol=self.to_canonical_symbol(t.get("symbol", "")),
            last_price=_safe_float(t.get("lastPrice")),
            high_24h=_safe_float(t.get("highPrice24h")),
            low_24h=_safe_float(t.get("lowPrice24h")),
            volume_24h=_safe_float(t.get("volume24h")),
            price_change_pct=_safe_float(t.get("price24hPcnt")),
            timestamp=datetime.now(tz=timezone.utc),
        )

    def _parse_order_book(self, data: dict[str, Any], symbol: str) -> OrderBook | None:
        """Parse Bybit v5 order book response.

        Bids/asks come as ``[["price", "qty"], ...]`` inside ``result``.
        """
        raw_bids: list[list[str]] = data.get("b", [])
        raw_asks: list[list[str]] = data.get("a", [])
        bids = tuple(
            OrderBookLevel(price=_safe_float(b[0]), quantity=_safe_float(b[1]))
            for b in raw_bids
            if len(b) >= 2
        )
        asks = tuple(
            OrderBookLevel(price=_safe_float(a[0]), quantity=_safe_float(a[1]))
            for a in raw_asks
            if len(a) >= 2
        )
        return OrderBook(
            symbol=self.to_canonical_symbol(symbol),
            bids=bids,
            asks=asks,
            timestamp=datetime.now(tz=timezone.utc),
        )

    def _parse_funding_rate(self, data: dict[str, Any]) -> FundingRate | None:
        """Parse Bybit v5 funding rate response.

        ``result.list`` contains funding info dicts.
        """
        items: list[dict[str, Any]] = data.get("list", [])
        if not items:
            return None
        f = items[0]
        next_ts = f.get("nextFundingTime")
        return FundingRate(
            symbol=self.to_canonical_symbol(f.get("symbol", "")),
            funding_rate=_safe_float(f.get("fundingRate")),
            mark_price=_safe_float(f.get("markPrice")),
            next_funding_time=_ts_to_datetime(next_ts) if next_ts else None,
            timestamp=datetime.now(tz=timezone.utc),
        )

    def _parse_balance(self, data: dict[str, Any]) -> AccountBalance | None:
        """Parse Bybit v5 wallet balance response.

        ``result.list`` contains account-level objects.
        """
        items: list[dict[str, Any]] = data.get("list", [])
        if not items:
            return None
        acct = items[0]
        return AccountBalance(
            total_balance=_safe_float(acct.get("totalEquity")),
            available_balance=_safe_float(acct.get("availableBalance")),
            unrealized_pnl=_safe_float(acct.get("totalPerpUPL", 0)),
            margin_balance=_safe_float(acct.get("totalMarginBalance", 0)),
            asset="USDT",
        )

    def _parse_positions(self, data: dict[str, Any]) -> list[ExchangePosition]:
        """Parse Bybit v5 position list.

        Bybit uses ``"Buy"``/``"Sell"`` for position side; we normalise to
        ``"LONG"``/``"SHORT"``.
        """
        items: list[dict[str, Any]] = data.get("list", [])
        positions: list[ExchangePosition] = []
        for p in items:
            raw_side = p.get("side", "")
            side = _bybit_side_to_canonical(raw_side)
            positions.append(
                ExchangePosition(
                    symbol=self.to_canonical_symbol(p.get("symbol", "")),
                    side=side,
                    quantity=_safe_float(p.get("size")),
                    entry_price=_safe_float(p.get("avgPrice", p.get("entryPrice"))),
                    mark_price=_safe_float(p.get("markPrice")),
                    unrealized_pnl=_safe_float(p.get("unrealisedPnl")),
                    leverage=int(_safe_float(p.get("leverage", 1))),
                    margin_mode=_bybit_trade_mode_to_canonical(p.get("tradeMode", "0")),
                )
            )
        return positions

    def _parse_income(self, data: dict[str, Any]) -> list[IncomeRecord]:
        """Parse Bybit v5 closed PnL / transaction log."""
        items: list[dict[str, Any]] = data.get("list", [])
        records: list[IncomeRecord] = []
        for item in items:
            records.append(
                IncomeRecord(
                    income_type=item.get("incomeType", "REALIZED_PNL"),
                    amount=_safe_float(item.get("amount", item.get("closedPnl", 0))),
                    asset=item.get("asset", "USDT"),
                    symbol=self.to_canonical_symbol(item.get("symbol", "")),
                    timestamp=_ts_to_datetime(item.get("updatedTime", item.get("time", 0))),
                )
            )
        return records

    def _parse_trades(self, data: dict[str, Any]) -> list[TradeRecord]:
        """Parse Bybit v5 execution list."""
        items: list[dict[str, Any]] = data.get("list", [])
        trades: list[TradeRecord] = []
        for t in items:
            trades.append(
                TradeRecord(
                    trade_id=t.get("execId", ""),
                    symbol=self.to_canonical_symbol(t.get("symbol", "")),
                    side=t.get("side", "").upper(),
                    price=_safe_float(t.get("execPrice", t.get("price"))),
                    quantity=_safe_float(t.get("execQty", t.get("qty"))),
                    commission=_safe_float(t.get("execFee", t.get("commission", 0))),
                    commission_asset=t.get("feeCurrency", "USDT"),
                    realized_pnl=_safe_float(t.get("closedPnl", 0)),
                    timestamp=_ts_to_datetime(t.get("execTime", t.get("time", 0))),
                    order_id=t.get("orderId", ""),
                )
            )
        return trades


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


def _bybit_side_to_canonical(side: str) -> str:
    """Convert Bybit position side to canonical ``LONG``/``SHORT``."""
    mapping = {"Buy": "LONG", "Sell": "SHORT", "buy": "LONG", "sell": "SHORT"}
    return mapping.get(side, side.upper())


def _bybit_trade_mode_to_canonical(trade_mode: str) -> str:
    """Convert Bybit ``tradeMode`` to canonical margin mode.

    Bybit v5: 0 = cross margin, 1 = isolated margin.
    """
    if trade_mode in ("1", "ISOLATED"):
        return "ISOLATED"
    return "CROSSED"


def _margin_mode_to_bybit(mode: str) -> str:
    """Convert canonical margin mode to Bybit ``tradeMode`` int string."""
    if mode.upper() == "ISOLATED":
        return "1"
    return "0"
