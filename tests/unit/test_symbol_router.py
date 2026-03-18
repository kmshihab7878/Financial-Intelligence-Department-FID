"""Tests for the SymbolRouter."""

from __future__ import annotations

from aiswarm.exchange.providers.aster import AsterExchangeProvider
from aiswarm.exchange.registry import ExchangeRegistry
from aiswarm.exchange.symbols import SymbolRouter
from aiswarm.execution.mcp_gateway import MockMCPGateway


def _make_registry() -> ExchangeRegistry:
    registry = ExchangeRegistry()
    registry.register(AsterExchangeProvider(MockMCPGateway()))
    return registry


class TestSymbolRouter:
    def test_resolve_default(self) -> None:
        registry = _make_registry()
        router = SymbolRouter(registry)

        assert router.resolve("BTCUSDT") == "aster"

    def test_resolve_explicit_mapping(self) -> None:
        registry = _make_registry()
        router = SymbolRouter(registry)
        router.add_mapping("AAPL", "ib")

        assert router.resolve("AAPL") == "ib"
        assert router.resolve("BTCUSDT") == "aster"  # still default

    def test_add_mappings(self) -> None:
        registry = _make_registry()
        router = SymbolRouter(registry)
        router.add_mappings({"AAPL": "ib", "GOOGL": "ib"})

        assert router.resolve("AAPL") == "ib"
        assert router.resolve("GOOGL") == "ib"
        assert router.resolve("BTCUSDT") == "aster"

    def test_get_exchange_for_symbol_alias(self) -> None:
        registry = _make_registry()
        router = SymbolRouter(registry)

        assert router.get_exchange_for_symbol("ETHUSDT") == "aster"

    def test_explicit_mappings_property(self) -> None:
        registry = _make_registry()
        router = SymbolRouter(registry)
        router.add_mapping("AAPL", "ib")

        mappings = router.explicit_mappings
        assert mappings == {"AAPL": "ib"}
        # Should return a copy
        mappings["FOO"] = "bar"
        assert "FOO" not in router.explicit_mappings
