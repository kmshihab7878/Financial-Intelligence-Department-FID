"""Tests for the ExchangeRegistry."""

from __future__ import annotations

import pytest

from aiswarm.exchange.providers.aster import AsterExchangeProvider
from aiswarm.exchange.registry import ExchangeRegistry
from aiswarm.execution.mcp_gateway import MockMCPGateway


def _make_provider() -> AsterExchangeProvider:
    return AsterExchangeProvider(MockMCPGateway())


class TestExchangeRegistry:
    def test_register_and_get(self) -> None:
        registry = ExchangeRegistry()
        provider = _make_provider()
        registry.register(provider)

        assert registry.get("aster") is provider

    def test_get_missing_raises(self) -> None:
        registry = ExchangeRegistry()
        with pytest.raises(KeyError, match="binance"):
            registry.get("binance")

    def test_auto_default(self) -> None:
        registry = ExchangeRegistry()
        provider = _make_provider()
        registry.register(provider)

        assert registry.get_default() is provider
        assert registry.default_exchange_id == "aster"

    def test_explicit_default(self) -> None:
        registry = ExchangeRegistry(default_exchange_id="aster")
        provider = _make_provider()
        registry.register(provider)

        assert registry.get_default() is provider

    def test_set_default(self) -> None:
        registry = ExchangeRegistry()
        provider = _make_provider()
        registry.register(provider)
        registry.set_default("aster")

        assert registry.default_exchange_id == "aster"

    def test_set_default_unknown_raises(self) -> None:
        registry = ExchangeRegistry()
        with pytest.raises(KeyError):
            registry.set_default("unknown")

    def test_no_providers_raises_on_get_default(self) -> None:
        registry = ExchangeRegistry()
        with pytest.raises(RuntimeError, match="No exchange providers"):
            registry.get_default()

    def test_contains(self) -> None:
        registry = ExchangeRegistry()
        provider = _make_provider()
        registry.register(provider)

        assert "aster" in registry
        assert "binance" not in registry

    def test_len(self) -> None:
        registry = ExchangeRegistry()
        assert len(registry) == 0
        registry.register(_make_provider())
        assert len(registry) == 1

    def test_registered_ids(self) -> None:
        registry = ExchangeRegistry()
        registry.register(_make_provider())
        assert registry.registered_ids == ["aster"]
