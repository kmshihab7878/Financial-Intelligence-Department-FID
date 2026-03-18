"""Canonical exchange data types.

These types are exchange-agnostic representations of market data, account
state, and trade records. All exchange providers parse their native formats
into these canonical types so that consuming code never depends on any
specific exchange's response schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


# --- Market Data Types ---


@dataclass(frozen=True)
class OHLCV:
    """Single OHLCV candle."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str


@dataclass(frozen=True)
class Ticker:
    """24h ticker summary."""

    symbol: str
    last_price: float
    high_24h: float
    low_24h: float
    volume_24h: float
    price_change_pct: float
    timestamp: datetime


@dataclass(frozen=True)
class OrderBookLevel:
    """Single order book price level."""

    price: float
    quantity: float


@dataclass(frozen=True)
class OrderBook:
    """Order book snapshot."""

    symbol: str
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]
    timestamp: datetime

    @property
    def spread(self) -> float:
        if self.bids and self.asks:
            return self.asks[0].price - self.bids[0].price
        return 0.0

    @property
    def spread_bps(self) -> float:
        if self.bids and self.asks and self.asks[0].price > 0:
            mid = (self.asks[0].price + self.bids[0].price) / 2
            return (self.spread / mid) * 10000
        return 0.0

    @property
    def bid_depth(self) -> float:
        return sum(level.price * level.quantity for level in self.bids)

    @property
    def ask_depth(self) -> float:
        return sum(level.price * level.quantity for level in self.asks)


@dataclass(frozen=True)
class FundingRate:
    """Funding rate data for perpetual futures."""

    symbol: str
    funding_rate: float
    mark_price: float
    next_funding_time: datetime | None
    timestamp: datetime


# --- Account Data Types ---


class IncomeType(str, Enum):
    REALIZED_PNL = "REALIZED_PNL"
    FUNDING_FEE = "FUNDING_FEE"
    COMMISSION = "COMMISSION"
    TRANSFER = "TRANSFER"


@dataclass(frozen=True)
class AccountBalance:
    """Account balance summary."""

    total_balance: float
    available_balance: float
    unrealized_pnl: float
    margin_balance: float
    asset: str = "USDT"


@dataclass(frozen=True)
class ExchangePosition:
    """Position from exchange."""

    symbol: str
    side: str  # "LONG" or "SHORT"
    quantity: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    leverage: int
    margin_mode: str  # "ISOLATED" or "CROSSED"


@dataclass(frozen=True)
class TradeRecord:
    """Single trade/fill record."""

    trade_id: str
    symbol: str
    side: str
    price: float
    quantity: float
    commission: float
    commission_asset: str
    realized_pnl: float
    timestamp: datetime
    order_id: str = ""


@dataclass(frozen=True)
class IncomeRecord:
    """Income/P&L record."""

    income_type: str
    amount: float
    asset: str
    symbol: str
    timestamp: datetime


# --- Exchange Metadata Types ---


@dataclass(frozen=True)
class ExchangeInfo:
    """Contract/pair specifications."""

    symbol: str
    base_asset: str
    quote_asset: str
    price_precision: int
    quantity_precision: int
    min_quantity: float
    max_quantity: float
    tick_size: float
    status: str


@dataclass(frozen=True)
class LeverageBracket:
    """Leverage tier from exchange."""

    bracket: int
    initial_leverage: int
    notional_cap: float
    notional_floor: float
    maintenance_margin_rate: float
