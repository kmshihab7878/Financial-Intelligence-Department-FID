"""Configuration for the autonomous trading loop."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LoopConfig:
    """Timing and behavior configuration for the trading loop.

    All intervals are in seconds.
    """

    # Core loop timing
    cycle_interval: float = 60.0  # Seconds between full trading cycles
    portfolio_sync_interval: float = 30.0  # How often to sync balances/positions
    fill_sync_interval: float = 15.0  # How often to poll for fills
    reconciliation_interval: float = 60.0  # How often to run reconciliation

    # Market data
    klines_interval: str = "1h"  # Candle interval for agents
    klines_limit: int = 100  # Number of candles to fetch

    # Symbols to trade
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT")

    # Account setup
    default_leverage: int = 1
    default_margin_mode: str = "ISOLATED"

    # Safety
    max_consecutive_errors: int = 5  # Halt after N consecutive errors
    heartbeat_interval: float = 10.0  # Seconds between heartbeat emissions
    order_timeout_seconds: float = 300.0  # Cancel orders older than this
