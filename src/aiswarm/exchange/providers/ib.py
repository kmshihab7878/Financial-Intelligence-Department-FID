"""Interactive Brokers exchange provider.

Encapsulates ALL mcp__ib__ tool name references. No other module in the
codebase should contain hardcoded IB MCP tool names -- they all go through
this provider.

Key IB-specific behaviors:
  - Symbols are stock tickers (AAPL, SPY) not slash-pairs
  - Uses conId (contract ID) for precise instrument identification
  - secType: STK (stock), OPT (options), FUT (futures), CASH (forex)
  - No funding rate, crypto-style leverage, or margin mode support
  - Numeric orderId (converted to string for compatibility)
  - Trade sides are BOT/SLD (mapped to canonical BUY/SELL)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from aiswarm.exchange.provider import AssetClass, ExchangeProvider
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

# --- IB MCP tool name constants ---

_TOOL_CREATE_ORDER = "mcp__ib__create_order"
_TOOL_CANCEL_ORDER = "mcp__ib__cancel_order"
_TOOL_CANCEL_ALL_ORDERS = "mcp__ib__cancel_all_orders"
_TOOL_GET_ORDER = "mcp__ib__get_order"
_TOOL_GET_MY_TRADES = "mcp__ib__get_my_trades"
_TOOL_GET_BALANCE = "mcp__ib__get_balance"
_TOOL_GET_POSITIONS = "mcp__ib__get_positions"
_TOOL_GET_KLINES = "mcp__ib__get_klines"
_TOOL_GET_TICKER = "mcp__ib__get_ticker"
_TOOL_GET_ORDER_BOOK = "mcp__ib__get_order_book"

# --- IB side mappings ---

_IB_SIDE_TO_CANONICAL = {"BOT": "BUY", "SLD": "SELL"}
_CANONICAL_SIDE_TO_IB = {"BUY": "BUY", "SELL": "SELL"}

# --- IB secType mappings ---

_VENUE_TO_SEC_TYPE = {
    "stocks": "STK",
    "options": "OPT",
    "futures": "FUT",
    "forex": "CASH",
}

# Known crypto tickers on IB that use the TICKER+USD format
_CRYPTO_TICKERS = frozenset(
    {
        "BTC",
        "ETH",
        "LTC",
        "BCH",
        "XRP",
        "ADA",
        "DOT",
        "SOL",
        "DOGE",
        "AVAX",
        "LINK",
        "MATIC",
        "UNI",
        "SHIB",
        "ALGO",
    }
)

# Regex: matches patterns like BTCUSD, ETHUSD (known crypto + USD suffix)
_CRYPTO_USD_RE = re.compile(r"^([A-Z]{2,5})(USD)$")


class IBExchangeProvider(ExchangeProvider):
    """Interactive Brokers exchange provider.

    Wraps the MCPGateway into a clean ExchangeProvider interface.
    All IB-specific MCP tool names are encapsulated here.
    """

    def __init__(
        self,
        gateway: MCPGateway,
        account_id: str = "",
    ) -> None:
        self.gateway = gateway
        self.account_id = account_id

    @property
    def exchange_id(self) -> str:
        return "ib"

    @property
    def supported_asset_classes(self) -> AssetClass:
        return AssetClass.STOCKS | AssetClass.OPTIONS | AssetClass.FUTURES | AssetClass.FOREX

    # --- Symbol normalization ---

    def normalize_symbol(self, canonical: str) -> str:
        """Convert canonical symbol to IB format.

        - "AAPL" -> "AAPL"  (stock ticker, unchanged)
        - "BTC/USD" -> "BTC" (strip quote for crypto on IB)
        - "EUR/USD" -> "EUR" (strip quote for forex)
        """
        if "/" in canonical:
            base, _quote = canonical.split("/", 1)
            return base
        return canonical

    def to_canonical_symbol(self, exchange_sym: str) -> str:
        """Convert IB-native symbol to canonical format.

        - "AAPL" -> "AAPL"     (plain stock ticker)
        - "BTCUSD" -> "BTC/USD" (crypto pair detected)
        """
        match = _CRYPTO_USD_RE.match(exchange_sym)
        if match and match.group(1) in _CRYPTO_TICKERS:
            return f"{match.group(1)}/{match.group(2)}"
        return exchange_sym

    # --- Market Data ---

    def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
    ) -> list[OHLCV]:
        response = self._call_safe(
            _TOOL_GET_KLINES,
            {"symbol": symbol, "interval": interval, "limit": limit},
        )
        if response is None:
            return []
        return self._parse_klines(response, symbol)

    def get_ticker(self, symbol: str) -> Ticker | None:
        response = self._call_safe(_TOOL_GET_TICKER, {"symbol": symbol})
        if response is None:
            return None
        return self._parse_ticker(response)

    def get_order_book(self, symbol: str) -> OrderBook | None:
        response = self._call_safe(_TOOL_GET_ORDER_BOOK, {"symbol": symbol})
        if response is None:
            return None
        return self._parse_order_book(response, symbol)

    def get_funding_rate(self, symbol: str) -> FundingRate | None:
        """IB does not support funding rates. Always returns None."""
        return None

    # --- Account ---

    def get_balance(self) -> AccountBalance | None:
        params: dict[str, Any] = {}
        if self.account_id:
            params["accountId"] = self.account_id
        response = self._call_safe(_TOOL_GET_BALANCE, params)
        if response is None:
            return None
        return self._parse_balance(response)

    def get_positions(self) -> list[ExchangePosition]:
        params: dict[str, Any] = {}
        if self.account_id:
            params["accountId"] = self.account_id
        response = self._call_safe(_TOOL_GET_POSITIONS, params)
        if response is None:
            return []
        return self._parse_positions(response)

    # --- Trading ---

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "MARKET",
        price: float | None = None,
        venue: str = "stocks",
        **kwargs: Any,
    ) -> dict[str, Any]:
        sec_type = _VENUE_TO_SEC_TYPE.get(venue, "STK")
        params: dict[str, Any] = {
            "symbol": self.normalize_symbol(symbol),
            "side": side,
            "orderType": order_type,
            "quantity": quantity,
            "secType": sec_type,
        }
        if self.account_id:
            params["accountId"] = self.account_id
        if price is not None:
            params["price"] = price
            params["tif"] = kwargs.get("tif", "GTC")

        con_id = kwargs.get("conId")
        if con_id is not None:
            params["conId"] = con_id

        # Forward any additional IB-specific kwargs
        for key, value in kwargs.items():
            if key not in ("tif", "conId"):
                params[key] = value

        response = self.gateway.call_tool(_TOOL_CREATE_ORDER, params)

        # Normalize orderId to string for cross-exchange compatibility
        if "orderId" in response:
            response["orderId"] = str(response["orderId"])

        return response

    def cancel_order(
        self,
        symbol: str,
        order_id: str,
        venue: str = "stocks",
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "symbol": self.normalize_symbol(symbol),
            "orderId": order_id,
        }
        if self.account_id:
            params["accountId"] = self.account_id
        return self.gateway.call_tool(_TOOL_CANCEL_ORDER, params)

    def cancel_all_orders(
        self,
        symbol: str,
        venue: str = "stocks",
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "symbol": self.normalize_symbol(symbol),
        }
        if self.account_id:
            params["accountId"] = self.account_id
        return self.gateway.call_tool(_TOOL_CANCEL_ALL_ORDERS, params)

    def get_order_status(
        self,
        symbol: str,
        order_id: str,
        venue: str = "stocks",
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "symbol": self.normalize_symbol(symbol),
            "orderId": order_id,
        }
        if self.account_id:
            params["accountId"] = self.account_id
        return self.gateway.call_tool(_TOOL_GET_ORDER, params)

    def get_my_trades(
        self,
        symbol: str,
        venue: str = "stocks",
    ) -> list[TradeRecord]:
        response = self._call_safe(
            _TOOL_GET_MY_TRADES,
            {"symbol": self.normalize_symbol(symbol)},
        )
        if response is None:
            return []
        return self._parse_trades(response)

    # --- Leverage/Margin (Not supported on IB) ---

    def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        """IB does not support crypto-style leverage setting."""
        raise NotImplementedError(f"{self.exchange_id} does not support set_leverage")

    def set_margin_mode(self, symbol: str, mode: str) -> dict[str, Any]:
        """IB does not support crypto-style margin mode setting."""
        raise NotImplementedError(f"{self.exchange_id} does not support set_margin_mode")

    # --- Parsing helpers ---

    def _parse_klines(
        self,
        data: Any,
        symbol: str,
    ) -> list[OHLCV]:
        """Parse IB historical data bars into canonical OHLCV.

        IB format: {"t": epoch, "o": float, "h": float, "l": float, "c": float, "v": int}
        """
        bars: list[dict[str, Any]] = data if isinstance(data, list) else data.get("bars", [])
        result: list[OHLCV] = []
        for bar in bars:
            try:
                ts = datetime.fromtimestamp(float(bar["t"]), tz=timezone.utc)
                result.append(
                    OHLCV(
                        timestamp=ts,
                        open=float(bar["o"]),
                        high=float(bar["h"]),
                        low=float(bar["l"]),
                        close=float(bar["c"]),
                        volume=float(bar["v"]),
                        symbol=symbol,
                    )
                )
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning(
                    "Failed to parse IB kline bar",
                    extra={"extra_json": {"bar": bar, "error": str(exc)}},
                )
        return result

    def _parse_ticker(self, data: dict[str, Any]) -> Ticker:
        """Parse IB ticker snapshot into canonical Ticker.

        IB format: {"symbol": "AAPL", "last": 155.0, "high": 156.0,
                     "low": 153.0, "volume": 50000000, "change": 1.5}
        """
        last = float(data.get("last", 0))
        high = float(data.get("high", 0))
        low = float(data.get("low", 0))

        # Compute pct change from absolute change if last > 0
        change = float(data.get("change", 0))
        prev = last - change
        pct = (change / prev * 100) if prev != 0 else 0.0

        return Ticker(
            symbol=str(data.get("symbol", "")),
            last_price=last,
            high_24h=high,
            low_24h=low,
            volume_24h=float(data.get("volume", 0)),
            price_change_pct=pct,
            timestamp=datetime.now(tz=timezone.utc),
        )

    def _parse_order_book(
        self,
        data: dict[str, Any],
        symbol: str,
    ) -> OrderBook:
        """Parse IB order book into canonical OrderBook.

        IB format: {"bids": [{"price": 154.95, "size": 100}],
                     "asks": [{"price": 155.05, "size": 200}]}
        Note: IB uses "size" not "quantity" for order book levels.
        """
        bids = tuple(
            OrderBookLevel(price=float(b["price"]), quantity=float(b["size"]))
            for b in data.get("bids", [])
        )
        asks = tuple(
            OrderBookLevel(price=float(a["price"]), quantity=float(a["size"]))
            for a in data.get("asks", [])
        )
        return OrderBook(
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=datetime.now(tz=timezone.utc),
        )

    def _parse_balance(self, data: dict[str, Any]) -> AccountBalance:
        """Parse IB account balance into canonical AccountBalance.

        IB format: {"accountId": "U1234", "totalCashValue": "100000",
                     "netLiquidation": "250000", "unrealizedPnL": "5000",
                     "availableFunds": "80000"}
        """
        net_liq = float(data.get("netLiquidation", 0))
        available = float(data.get("availableFunds", 0))
        unrealized = float(data.get("unrealizedPnL", 0))
        total_cash = float(data.get("totalCashValue", 0))

        return AccountBalance(
            total_balance=net_liq,
            available_balance=available,
            unrealized_pnl=unrealized,
            margin_balance=total_cash,
            asset="USD",
        )

    def _parse_positions(self, data: Any) -> list[ExchangePosition]:
        """Parse IB positions into canonical ExchangePosition list.

        IB format: [{"conid": 265598, "symbol": "AAPL", "position": 100,
                      "avgCost": 150.0, "mktPrice": 155.0, "unrealizedPnl": 500.0}]
        - "position" can be negative for short positions
        """
        positions_list: list[dict[str, Any]] = (
            data if isinstance(data, list) else data.get("positions", [])
        )
        result: list[ExchangePosition] = []
        for pos in positions_list:
            try:
                raw_qty = float(pos.get("position", 0))
                if raw_qty == 0:
                    continue  # skip flat positions

                side = "LONG" if raw_qty > 0 else "SHORT"
                quantity = abs(raw_qty)
                symbol_raw = str(pos.get("symbol", ""))
                canonical = self.to_canonical_symbol(symbol_raw)

                result.append(
                    ExchangePosition(
                        symbol=canonical,
                        side=side,
                        quantity=quantity,
                        entry_price=float(pos.get("avgCost", 0)),
                        mark_price=float(pos.get("mktPrice", 0)),
                        unrealized_pnl=float(pos.get("unrealizedPnl", 0)),
                        leverage=1,  # IB uses portfolio margin, not discrete leverage
                        margin_mode="PORTFOLIO",
                    )
                )
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning(
                    "Failed to parse IB position",
                    extra={"extra_json": {"position": pos, "error": str(exc)}},
                )
        return result

    def _parse_trades(self, data: Any) -> list[TradeRecord]:
        """Parse IB trade executions into canonical TradeRecord list.

        IB format: [{"execId": "E001", "symbol": "AAPL", "side": "BOT",
                      "price": 155.0, "shares": 100, "commission": 1.0,
                      "realizedPNL": 0.0, "time": "20240101-10:00:00"}]
        - Side: BOT -> BUY, SLD -> SELL
        """
        trades_list: list[dict[str, Any]] = (
            data if isinstance(data, list) else data.get("trades", [])
        )
        result: list[TradeRecord] = []
        for trade in trades_list:
            try:
                raw_side = str(trade.get("side", ""))
                canonical_side = _IB_SIDE_TO_CANONICAL.get(raw_side, raw_side)

                ts = self._parse_ib_timestamp(str(trade.get("time", "")))

                result.append(
                    TradeRecord(
                        trade_id=str(trade.get("execId", "")),
                        symbol=self.to_canonical_symbol(str(trade.get("symbol", ""))),
                        side=canonical_side,
                        price=float(trade.get("price", 0)),
                        quantity=float(trade.get("shares", 0)),
                        commission=float(trade.get("commission", 0)),
                        commission_asset="USD",
                        realized_pnl=float(trade.get("realizedPNL", 0)),
                        timestamp=ts,
                    )
                )
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning(
                    "Failed to parse IB trade",
                    extra={"extra_json": {"trade": trade, "error": str(exc)}},
                )
        return result

    @staticmethod
    def _parse_ib_timestamp(ts_str: str) -> datetime:
        """Parse IB timestamp format '20240101-10:00:00' to datetime."""
        if not ts_str:
            return datetime.now(tz=timezone.utc)
        try:
            return datetime.strptime(ts_str, "%Y%m%d-%H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            # Fall back to epoch if format doesn't match
            try:
                return datetime.fromtimestamp(float(ts_str), tz=timezone.utc)
            except (ValueError, OSError):
                return datetime.now(tz=timezone.utc)

    # --- Internal ---

    def _call_safe(self, tool_name: str, params: dict[str, Any]) -> Any | None:
        """Call a tool, returning None on error."""
        try:
            return self.gateway.call_tool(tool_name, params)
        except Exception as e:
            logger.warning(
                "IB MCP call failed",
                extra={"extra_json": {"tool": tool_name, "error": str(e)}},
            )
            return None
