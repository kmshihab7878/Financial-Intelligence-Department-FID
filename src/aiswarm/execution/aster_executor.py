"""Aster DEX execution adapter.

Handles order submission, cancellation, and status queries against Aster DEX.
Supports three execution modes:
  - paper: Log order intent, simulate fill using ticker price (no MCP calls)
  - shadow: Fetch real data but do NOT submit orders
  - live: Actually submit orders via MCP (requires explicit flags)

SAFETY: Live mode requires:
  - AIS_ENABLE_LIVE_TRADING=true environment variable
  - Valid risk approval token on every order
  - Leverage and margin mode set before first order
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from aiswarm.data.providers.aster_config import (
    AsterConfig,
    Venue,
    normalize_symbol,
)
from aiswarm.risk.limits import verify_risk_token
from aiswarm.types.orders import Order, Side
from aiswarm.utils.logging import get_logger
from aiswarm.utils.time import utc_now

logger = get_logger(__name__)


class ExecutionMode(str, Enum):
    PAPER = "paper"
    SHADOW = "shadow"
    LIVE = "live"


@dataclass(frozen=True)
class ExecutionResult:
    """Result of an order submission attempt."""

    success: bool
    order_id: str
    exchange_order_id: str | None
    status: str
    message: str
    fill_price: float | None = None
    fill_quantity: float | None = None
    timestamp: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class CancelResult:
    """Result of an order cancellation attempt."""

    success: bool
    order_id: str
    message: str


class AsterExecutor:
    """Execution adapter for Aster DEX.

    Does NOT make MCP calls directly. Instead, it prepares order parameters
    and returns them as structured dicts that the caller uses to invoke
    the appropriate MCP tool. This keeps the executor testable and decoupled.
    """

    def __init__(
        self,
        config: AsterConfig | None = None,
        mode: ExecutionMode = ExecutionMode.PAPER,
    ) -> None:
        self.config = config or AsterConfig.from_env()
        self.mode = mode
        self._paper_fills: list[ExecutionResult] = []
        self._validate_mode()

    def _validate_mode(self) -> None:
        """Ensure live mode has explicit authorization."""
        if self.mode == ExecutionMode.LIVE:
            enabled = os.environ.get("AIS_ENABLE_LIVE_TRADING", "false").lower()
            if enabled != "true":
                raise RuntimeError(
                    "Live trading requires AIS_ENABLE_LIVE_TRADING=true. "
                    "Set this environment variable explicitly to enable live execution."
                )
            if not self.config.has_account:
                raise RuntimeError("Live trading requires ASTER_ACCOUNT_ID to be set.")
            logger.warning("AsterExecutor initialized in LIVE mode")

    # --- Order Preparation ---

    def prepare_futures_order(self, order: Order) -> dict[str, Any]:
        """Prepare parameters for mcp__aster__create_order."""
        if not order.risk_approval_token:
            raise ValueError("Cannot submit order without risk approval token")
        if self.mode == ExecutionMode.LIVE:
            if not verify_risk_token(order.risk_approval_token, order.order_id):
                raise ValueError("Risk approval token is invalid or expired")

        symbol = normalize_symbol(order.symbol)
        params: dict[str, Any] = {
            "account_id": self.config.account_id,
            "symbol": symbol,
            "side": "BUY" if order.side == Side.BUY else "SELL",
            "order_type": "LIMIT" if order.limit_price else "MARKET",
            "quantity": order.quantity,
        }
        if order.limit_price:
            params["price"] = order.limit_price
            params["time_in_force"] = "GTC"
        return params

    def prepare_spot_order(self, order: Order) -> dict[str, Any]:
        """Prepare parameters for mcp__aster__create_spot_order."""
        if not order.risk_approval_token:
            raise ValueError("Cannot submit order without risk approval token")
        if self.mode == ExecutionMode.LIVE:
            if not verify_risk_token(order.risk_approval_token, order.order_id):
                raise ValueError("Risk approval token is invalid or expired")

        symbol = normalize_symbol(order.symbol)
        params: dict[str, Any] = {
            "account_id": self.config.account_id,
            "symbol": symbol,
            "side": "BUY" if order.side == Side.BUY else "SELL",
            "order_type": "LIMIT" if order.limit_price else "MARKET",
            "quantity": order.quantity,
        }
        if order.limit_price:
            params["price"] = order.limit_price
            params["time_in_force"] = "GTC"
        return params

    def simulate_paper_fill(self, order: Order, current_price: float) -> ExecutionResult:
        """Simulate a fill in paper mode using current market price."""
        fill_price = order.limit_price if order.limit_price else current_price
        result = ExecutionResult(
            success=True,
            order_id=order.order_id,
            exchange_order_id=f"paper_{order.order_id}",
            status="FILLED",
            message=f"Paper fill at {fill_price:.4f}",
            fill_price=fill_price,
            fill_quantity=order.quantity,
        )
        self._paper_fills.append(result)
        logger.info(
            "Paper order filled",
            extra={
                "extra_json": {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "side": order.side.value,
                    "price": fill_price,
                    "quantity": order.quantity,
                }
            },
        )
        return result

    # --- Cancellation Preparation ---

    def prepare_cancel_order(
        self,
        symbol: str,
        order_id: str,
        venue: Venue = Venue.FUTURES,
    ) -> dict[str, Any]:
        """Prepare parameters for cancel order MCP call."""
        tool = "cancel_order" if venue == Venue.FUTURES else "cancel_spot_order"
        return {
            "tool": f"mcp__aster__{tool}",
            "account_id": self.config.account_id,
            "symbol": normalize_symbol(symbol),
            "order_id": order_id,
        }

    def prepare_cancel_all(
        self,
        symbol: str,
        venue: Venue = Venue.FUTURES,
    ) -> dict[str, Any]:
        """Prepare parameters for cancel all orders (KILL SWITCH).

        This is the atomic emergency stop — cancels ALL open orders for a symbol.
        """
        tool = "cancel_all_orders" if venue == Venue.FUTURES else "cancel_spot_all_orders"
        return {
            "tool": f"mcp__aster__{tool}",
            "account_id": self.config.account_id,
            "symbol": normalize_symbol(symbol),
        }

    def prepare_emergency_cancel_all(self, symbols: list[str]) -> list[dict[str, Any]]:
        """Prepare cancel-all for multiple symbols across both venues.

        Used by the kill switch for total emergency shutdown.
        """
        cancels: list[dict[str, Any]] = []
        for symbol in symbols:
            cancels.append(self.prepare_cancel_all(symbol, Venue.FUTURES))
            cancels.append(self.prepare_cancel_all(symbol, Venue.SPOT))
        return cancels

    # --- Status Query Preparation ---

    def prepare_get_order(
        self,
        symbol: str,
        order_id: str,
        venue: Venue = Venue.FUTURES,
    ) -> dict[str, Any]:
        """Prepare parameters for order status query."""
        tool = "get_order" if venue == Venue.FUTURES else "get_spot_order"
        return {
            "tool": f"mcp__aster__{tool}",
            "account_id": self.config.account_id,
            "symbol": normalize_symbol(symbol),
            "order_id": order_id,
        }

    def prepare_get_fills(
        self,
        symbol: str,
        venue: Venue = Venue.FUTURES,
    ) -> dict[str, Any]:
        """Prepare parameters for trade/fill history query."""
        tool = "get_my_trades" if venue == Venue.FUTURES else "get_spot_my_trades"
        return {
            "tool": f"mcp__aster__{tool}",
            "account_id": self.config.account_id,
            "symbol": normalize_symbol(symbol),
        }

    # --- Leverage/Margin Control ---

    def prepare_set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        """Prepare parameters to set leverage before trading."""
        return {
            "tool": "mcp__aster__set_leverage",
            "account_id": self.config.account_id,
            "symbol": normalize_symbol(symbol),
            "leverage": leverage,
        }

    def prepare_set_margin_mode(self, symbol: str, mode: str = "ISOLATED") -> dict[str, Any]:
        """Prepare parameters to set margin mode (ISOLATED recommended)."""
        return {
            "tool": "mcp__aster__set_margin_mode",
            "account_id": self.config.account_id,
            "symbol": normalize_symbol(symbol),
            "margin_mode": mode,
        }

    # --- Paper Trading State ---

    @property
    def paper_fill_count(self) -> int:
        return len(self._paper_fills)

    @property
    def paper_fills(self) -> list[ExecutionResult]:
        return list(self._paper_fills)
