"""ExchangeProvider ABC — exchange-agnostic interface for trading operations.

Each exchange (Aster, Binance, Coinbase, Bybit, Interactive Brokers) implements
this ABC. The provider encapsulates all exchange-specific tool names, parameter
formatting, and response parsing. Consuming code depends only on this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Flag, auto
from typing import Any

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


class AssetClass(Flag):
    """Supported asset classes for an exchange."""

    SPOT = auto()
    FUTURES = auto()
    OPTIONS = auto()
    STOCKS = auto()
    FOREX = auto()


class Venue:
    """Standardized venue constants."""

    SPOT = "spot"
    FUTURES = "futures"


class ExchangeProvider(ABC):
    """Abstract base class for exchange providers.

    Each method either returns parsed canonical types or raw dicts (for
    operations where the exact response structure varies by exchange).
    Methods that are not supported by a specific exchange should raise
    ``NotImplementedError``.
    """

    @property
    @abstractmethod
    def exchange_id(self) -> str:
        """Unique identifier for this exchange (e.g. 'aster', 'binance')."""
        ...

    @property
    @abstractmethod
    def supported_asset_classes(self) -> AssetClass:
        """Asset classes supported by this exchange."""
        ...

    # --- Symbol normalization ---

    @abstractmethod
    def normalize_symbol(self, canonical: str) -> str:
        """Convert canonical symbol (e.g. 'BTC/USDT') to exchange format."""
        ...

    @abstractmethod
    def to_canonical_symbol(self, exchange_sym: str) -> str:
        """Convert exchange-native symbol to canonical format."""
        ...

    # --- Market Data ---

    @abstractmethod
    def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
    ) -> list[OHLCV]:
        """Fetch OHLCV candles for a symbol."""
        ...

    @abstractmethod
    def get_ticker(self, symbol: str) -> Ticker | None:
        """Fetch 24h ticker for a symbol."""
        ...

    @abstractmethod
    def get_order_book(self, symbol: str) -> OrderBook | None:
        """Fetch order book snapshot."""
        ...

    def get_funding_rate(self, symbol: str) -> FundingRate | None:
        """Fetch funding rate (futures only). Returns None if unsupported."""
        return None

    # --- Account ---

    @abstractmethod
    def get_balance(self) -> AccountBalance | None:
        """Fetch account balance summary."""
        ...

    @abstractmethod
    def get_positions(self) -> list[ExchangePosition]:
        """Fetch open positions."""
        ...

    def get_income(self) -> list[IncomeRecord]:
        """Fetch income/P&L records. Returns empty list if unsupported."""
        return []

    # --- Trading ---

    @abstractmethod
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
        """Place an order. Returns response dict with at least 'orderId'."""
        ...

    @abstractmethod
    def cancel_order(
        self,
        symbol: str,
        order_id: str,
        venue: str = "futures",
    ) -> dict[str, Any]:
        """Cancel a single order."""
        ...

    @abstractmethod
    def cancel_all_orders(
        self,
        symbol: str,
        venue: str = "futures",
    ) -> dict[str, Any]:
        """Cancel all open orders for a symbol."""
        ...

    def get_order_status(
        self,
        symbol: str,
        order_id: str,
        venue: str = "futures",
    ) -> dict[str, Any]:
        """Query order status. Default raises NotImplementedError."""
        raise NotImplementedError

    def get_my_trades(
        self,
        symbol: str,
        venue: str = "futures",
    ) -> list[TradeRecord]:
        """Fetch recent trades/fills. Default returns empty list."""
        return []

    # --- Optional: Leverage/Margin ---

    def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        """Set leverage for a symbol. Raises NotImplementedError if unsupported."""
        raise NotImplementedError(f"{self.exchange_id} does not support set_leverage")

    def set_margin_mode(self, symbol: str, mode: str) -> dict[str, Any]:
        """Set margin mode. Raises NotImplementedError if unsupported."""
        raise NotImplementedError(f"{self.exchange_id} does not support set_margin_mode")
