"""Binance exchange provider.

Encapsulates ALL mcp__binance__ tool name references. No other module in the
codebase should contain hardcoded Binance MCP tool names -- they all go through
this provider.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from aiswarm.data.providers.aster import AsterDataProvider
from aiswarm.data.providers.aster_config import (
    AsterConfig,
    normalize_symbol as binance_normalize,
    to_canonical_symbol as binance_to_canonical,
)
from aiswarm.exchange.provider import AssetClass, ExchangeProvider
from aiswarm.exchange.types import (
    AccountBalance,
    ExchangePosition,
    FundingRate,
    IncomeRecord,
    OHLCV,
    OrderBook,
    Ticker,
    TradeRecord,
)
from aiswarm.execution.mcp_gateway import MCPGateway
from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)

# --- Binance MCP tool name constants (all 19 unique tools) ---

_TOOL_CREATE_ORDER = "mcp__binance__create_order"
_TOOL_CREATE_SPOT_ORDER = "mcp__binance__create_spot_order"
_TOOL_CANCEL_ORDER = "mcp__binance__cancel_order"
_TOOL_CANCEL_SPOT_ORDER = "mcp__binance__cancel_spot_order"
_TOOL_CANCEL_ALL_ORDERS = "mcp__binance__cancel_all_orders"
_TOOL_CANCEL_SPOT_ALL_ORDERS = "mcp__binance__cancel_spot_all_orders"
_TOOL_GET_ORDER = "mcp__binance__get_order"
_TOOL_GET_SPOT_ORDER = "mcp__binance__get_spot_order"
_TOOL_GET_MY_TRADES = "mcp__binance__get_my_trades"
_TOOL_GET_SPOT_MY_TRADES = "mcp__binance__get_spot_my_trades"
_TOOL_GET_BALANCE = "mcp__binance__get_balance"
_TOOL_GET_POSITIONS = "mcp__binance__get_positions"
_TOOL_GET_INCOME = "mcp__binance__get_income"
_TOOL_GET_KLINES = "mcp__binance__get_klines"
_TOOL_GET_FUNDING_RATE = "mcp__binance__get_funding_rate"
_TOOL_GET_TICKER = "mcp__binance__get_ticker"
_TOOL_GET_ORDER_BOOK = "mcp__binance__get_order_book"
_TOOL_SET_LEVERAGE = "mcp__binance__set_leverage"
_TOOL_SET_MARGIN_MODE = "mcp__binance__set_margin_mode"


@dataclass(frozen=True)
class BinanceConfig:
    """Configuration for Binance connectivity."""

    account_id: str = ""
    rate_limit_calls_per_second: float = 20.0  # 1200 req/min
    request_timeout_seconds: int = 10
    max_retries: int = 3

    @classmethod
    def from_env(cls) -> BinanceConfig:
        """Build config from environment variables."""
        return cls(
            account_id=os.environ.get("BINANCE_ACCOUNT_ID", ""),
        )

    @property
    def has_account(self) -> bool:
        return bool(self.account_id)


class BinanceExchangeProvider(ExchangeProvider):
    """Binance exchange provider.

    Wraps the MCPGateway + AsterDataProvider (Binance-compatible parser) into
    a clean ExchangeProvider interface. Binance uses the same response format
    as Aster (since Aster mimics Binance), so the AsterDataProvider parser is
    reused for response parsing.

    All Binance-specific MCP tool names are encapsulated here.
    """

    def __init__(
        self,
        gateway: MCPGateway,
        config: BinanceConfig | None = None,
        parser: AsterDataProvider | None = None,
    ) -> None:
        self.gateway = gateway
        self.config = config or BinanceConfig.from_env()
        # Reuse Aster parser -- Binance response format is identical
        self.parser = parser or AsterDataProvider(AsterConfig(account_id=self.config.account_id))

    @property
    def exchange_id(self) -> str:
        return "binance"

    @property
    def supported_asset_classes(self) -> AssetClass:
        return AssetClass.SPOT | AssetClass.FUTURES

    # --- Symbol normalization ---

    def normalize_symbol(self, canonical: str) -> str:
        return binance_normalize(canonical)

    def to_canonical_symbol(self, exchange_sym: str) -> str:
        return binance_to_canonical(exchange_sym)

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
        return self.parser.parse_klines(response, symbol)

    def get_ticker(self, symbol: str) -> Ticker | None:
        response = self._call_safe(_TOOL_GET_TICKER, {"symbol": symbol})
        if response is None:
            return None
        return self.parser.parse_ticker_response(response)

    def get_order_book(self, symbol: str) -> OrderBook | None:
        response = self._call_safe(_TOOL_GET_ORDER_BOOK, {"symbol": symbol})
        if response is None:
            return None
        return self.parser.parse_orderbook_response(response, symbol)

    def get_funding_rate(self, symbol: str) -> FundingRate | None:
        response = self._call_safe(_TOOL_GET_FUNDING_RATE, {"symbol": symbol})
        if response is None:
            return None
        return self.parser.parse_funding_response(response)

    # --- Account ---

    def get_balance(self) -> AccountBalance | None:
        response = self._call_safe(_TOOL_GET_BALANCE, {})
        if response is None:
            return None
        return self.parser.parse_balance_response(response)

    def get_positions(self) -> list[ExchangePosition]:
        response = self._call_safe(_TOOL_GET_POSITIONS, {})
        if response is None:
            return []
        return self.parser.parse_positions_response(response)

    def get_income(self) -> list[IncomeRecord]:
        response = self._call_safe(_TOOL_GET_INCOME, {})
        if response is None:
            return []
        return self.parser.parse_income_response(response)

    # --- Trading ---

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
        params: dict[str, Any] = {
            "account_id": self.config.account_id,
            "symbol": self.normalize_symbol(symbol),
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
        }
        if price is not None:
            params["price"] = price
            params["time_in_force"] = kwargs.get("time_in_force", "GTC")

        # Binance futures supports reduceOnly parameter
        if venue == "futures" and "reduceOnly" in kwargs:
            params["reduceOnly"] = kwargs["reduceOnly"]

        params.update({k: v for k, v in kwargs.items() if k not in ("time_in_force", "reduceOnly")})

        tool = _TOOL_CREATE_ORDER if venue == "futures" else _TOOL_CREATE_SPOT_ORDER
        return self.gateway.call_tool(tool, params)

    def cancel_order(
        self,
        symbol: str,
        order_id: str,
        venue: str = "futures",
    ) -> dict[str, Any]:
        params = {
            "account_id": self.config.account_id,
            "symbol": self.normalize_symbol(symbol),
            "order_id": order_id,
        }
        tool = _TOOL_CANCEL_ORDER if venue == "futures" else _TOOL_CANCEL_SPOT_ORDER
        return self.gateway.call_tool(tool, params)

    def cancel_all_orders(
        self,
        symbol: str,
        venue: str = "futures",
    ) -> dict[str, Any]:
        params = {
            "account_id": self.config.account_id,
            "symbol": self.normalize_symbol(symbol),
        }
        tool = _TOOL_CANCEL_ALL_ORDERS if venue == "futures" else _TOOL_CANCEL_SPOT_ALL_ORDERS
        return self.gateway.call_tool(tool, params)

    def get_order_status(
        self,
        symbol: str,
        order_id: str,
        venue: str = "futures",
    ) -> dict[str, Any]:
        params = {
            "account_id": self.config.account_id,
            "symbol": self.normalize_symbol(symbol),
            "order_id": order_id,
        }
        tool = _TOOL_GET_ORDER if venue == "futures" else _TOOL_GET_SPOT_ORDER
        return self.gateway.call_tool(tool, params)

    def get_my_trades(
        self,
        symbol: str,
        venue: str = "futures",
    ) -> list[TradeRecord]:
        tool = _TOOL_GET_MY_TRADES if venue == "futures" else _TOOL_GET_SPOT_MY_TRADES
        response = self._call_safe(tool, {"symbol": symbol})
        if response is None:
            return []
        return self.parser.parse_trades_response(response)

    # --- Leverage/Margin ---

    def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        params = {
            "account_id": self.config.account_id,
            "symbol": self.normalize_symbol(symbol),
            "leverage": leverage,
        }
        return self.gateway.call_tool(_TOOL_SET_LEVERAGE, params)

    def set_margin_mode(self, symbol: str, mode: str) -> dict[str, Any]:
        params = {
            "account_id": self.config.account_id,
            "symbol": self.normalize_symbol(symbol),
            "margin_mode": mode,
        }
        return self.gateway.call_tool(_TOOL_SET_MARGIN_MODE, params)

    # --- Internal ---

    def _call_safe(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Call a tool, returning None on error."""
        try:
            return self.gateway.call_tool(tool_name, params)
        except Exception as e:
            logger.warning(
                "Binance MCP call failed",
                extra={"extra_json": {"tool": tool_name, "error": str(e)}},
            )
            return None
