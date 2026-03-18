"""Exchange registry — manages multiple exchange providers."""

from __future__ import annotations

from aiswarm.exchange.provider import ExchangeProvider
from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)


class ExchangeRegistry:
    """Registry of exchange providers.

    Provides lookup by exchange ID and default provider resolution.
    Thread-safe for reads after initial registration.
    """

    def __init__(self, default_exchange_id: str = "") -> None:
        self._providers: dict[str, ExchangeProvider] = {}
        self._default_exchange_id = default_exchange_id

    def register(self, provider: ExchangeProvider) -> None:
        """Register an exchange provider."""
        self._providers[provider.exchange_id] = provider
        logger.info(
            "Exchange provider registered",
            extra={"extra_json": {"exchange_id": provider.exchange_id}},
        )
        # Auto-set default if this is the first provider
        if not self._default_exchange_id:
            self._default_exchange_id = provider.exchange_id

    def get(self, exchange_id: str) -> ExchangeProvider:
        """Get a provider by exchange ID. Raises KeyError if not found."""
        if exchange_id not in self._providers:
            raise KeyError(
                f"Exchange '{exchange_id}' not registered. "
                f"Available: {sorted(self._providers.keys())}"
            )
        return self._providers[exchange_id]

    def get_default(self) -> ExchangeProvider:
        """Get the default exchange provider. Raises RuntimeError if none registered."""
        if not self._default_exchange_id:
            raise RuntimeError("No exchange providers registered")
        return self.get(self._default_exchange_id)

    def set_default(self, exchange_id: str) -> None:
        """Set the default exchange by ID. Raises KeyError if not registered."""
        if exchange_id not in self._providers:
            raise KeyError(f"Exchange '{exchange_id}' not registered")
        self._default_exchange_id = exchange_id

    @property
    def default_exchange_id(self) -> str:
        return self._default_exchange_id

    @property
    def registered_ids(self) -> list[str]:
        return sorted(self._providers.keys())

    def __contains__(self, exchange_id: str) -> bool:
        return exchange_id in self._providers

    def __len__(self) -> int:
        return len(self._providers)
