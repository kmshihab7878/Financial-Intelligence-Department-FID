"""Portfolio tracker formatters — convert snapshots to service-specific payloads."""

from __future__ import annotations

from typing import Any

from aiswarm.types.portfolio import PortfolioSnapshot


def format_coingecko(snapshot: PortfolioSnapshot) -> dict[str, Any]:
    """Format a PortfolioSnapshot for CoinGecko portfolio API."""
    return {
        "total_value_usd": snapshot.nav,
        "cash_usd": snapshot.cash,
        "positions": [
            {
                "coin_id": pos.symbol.lower().replace("/", ""),
                "quantity": pos.quantity,
                "avg_buy_price": pos.avg_price,
                "current_price": pos.market_price,
            }
            for pos in snapshot.positions
        ],
        "timestamp": snapshot.timestamp.isoformat(),
    }


def format_zapper(snapshot: PortfolioSnapshot) -> dict[str, Any]:
    """Format a PortfolioSnapshot for Zapper portfolio API."""
    return {
        "net_worth": snapshot.nav,
        "assets": [
            {
                "token": pos.symbol,
                "balance": pos.quantity,
                "price": pos.market_price,
                "value": pos.quantity * pos.market_price,
            }
            for pos in snapshot.positions
        ],
        "updated_at": snapshot.timestamp.isoformat(),
    }


def format_debank(snapshot: PortfolioSnapshot) -> dict[str, Any]:
    """Format a PortfolioSnapshot for DeBank portfolio API."""
    return {
        "total_usd_value": snapshot.nav,
        "token_list": [
            {
                "symbol": pos.symbol,
                "amount": pos.quantity,
                "price": pos.market_price,
            }
            for pos in snapshot.positions
        ],
        "update_at": int(snapshot.timestamp.timestamp()),
    }
