"""Exchange abstraction layer.

Provides exchange-agnostic interfaces for market data, trading, and account
management. Each exchange implements the ExchangeProvider ABC; the
ExchangeRegistry resolves providers by exchange ID or symbol.
"""

from __future__ import annotations

from aiswarm.exchange.provider import AssetClass, ExchangeProvider
from aiswarm.exchange.registry import ExchangeRegistry
from aiswarm.exchange.symbols import SymbolRouter

__all__ = [
    "AssetClass",
    "ExchangeProvider",
    "ExchangeRegistry",
    "SymbolRouter",
]
