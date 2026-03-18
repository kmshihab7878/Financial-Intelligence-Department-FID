"""Tax export formatters — convert trade events to format-specific rows."""

from __future__ import annotations

from typing import Any


def format_csv_row(timestamp: str, payload: dict[str, Any]) -> list[str]:
    """Format a trade event as a generic CSV row."""
    symbol = payload.get("symbol", "")
    side = payload.get("side", "")
    price = payload.get("fill_price", 0)
    qty = payload.get("fill_quantity", 0)
    total = float(price) * float(qty)
    return [
        timestamp,
        "trade",
        symbol,
        side,
        str(qty),
        str(price),
        f"{total:.2f}",
        str(payload.get("commission", "0")),
        payload.get("commission_asset", "USDT"),
        str(payload.get("realized_pnl", "0")),
    ]


def format_koinly_row(timestamp: str, payload: dict[str, Any]) -> list[str]:
    """Format a trade event as a Koinly-compatible row."""
    symbol = payload.get("symbol", "")
    side = payload.get("side", "").upper()
    price = float(payload.get("fill_price", 0))
    qty = float(payload.get("fill_quantity", 0))
    total = price * qty
    fee = payload.get("commission", "0")

    if side == "BUY":
        return [
            timestamp,
            f"{total:.2f}",
            "USDT",
            str(qty),
            symbol.replace("USDT", "").replace("/", ""),
            str(fee),
            "USDT",
            f"{total:.2f}",
            "USD",
            "",
            f"Buy {symbol}",
            "",
        ]
    else:
        return [
            timestamp,
            str(qty),
            symbol.replace("USDT", "").replace("/", ""),
            f"{total:.2f}",
            "USDT",
            str(fee),
            "USDT",
            f"{total:.2f}",
            "USD",
            "",
            f"Sell {symbol}",
            "",
        ]


def format_cointracker_row(timestamp: str, payload: dict[str, Any]) -> list[str]:
    """Format a trade event as a CoinTracker-compatible row."""
    symbol = payload.get("symbol", "")
    side = payload.get("side", "").upper()
    price = float(payload.get("fill_price", 0))
    qty = float(payload.get("fill_quantity", 0))
    total = price * qty
    base = symbol.replace("USDT", "").replace("/", "")
    fee = payload.get("commission", "0")

    if side == "BUY":
        return [
            timestamp,
            "Buy",
            str(qty),
            base,
            f"{total:.2f}",
            "USDT",
            str(fee),
            "USDT",
        ]
    else:
        return [
            timestamp,
            "Sell",
            f"{total:.2f}",
            "USDT",
            str(qty),
            base,
            str(fee),
            "USDT",
        ]
