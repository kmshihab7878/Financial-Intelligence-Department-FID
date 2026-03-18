"""Symbol router — resolves which exchange handles a given symbol."""

from __future__ import annotations

from aiswarm.exchange.registry import ExchangeRegistry
from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)


class SymbolRouter:
    """Routes symbols to the appropriate exchange provider.

    Uses explicit symbol-to-exchange mappings from config. If no explicit
    mapping exists, falls back to the registry's default exchange.
    """

    def __init__(self, registry: ExchangeRegistry) -> None:
        self._registry = registry
        self._symbol_map: dict[str, str] = {}  # symbol -> exchange_id

    def add_mapping(self, symbol: str, exchange_id: str) -> None:
        """Map a symbol to a specific exchange."""
        self._symbol_map[symbol] = exchange_id

    def add_mappings(self, mappings: dict[str, str]) -> None:
        """Add multiple symbol-to-exchange mappings."""
        self._symbol_map.update(mappings)

    def resolve(self, symbol: str) -> str:
        """Resolve a symbol to an exchange ID.

        Returns the explicitly mapped exchange ID, or the default exchange ID.
        """
        if symbol in self._symbol_map:
            return self._symbol_map[symbol]
        return self._registry.default_exchange_id

    def get_exchange_for_symbol(self, symbol: str) -> str:
        """Alias for resolve()."""
        return self.resolve(symbol)

    @property
    def explicit_mappings(self) -> dict[str, str]:
        """Return a copy of explicit symbol-to-exchange mappings."""
        return dict(self._symbol_map)
