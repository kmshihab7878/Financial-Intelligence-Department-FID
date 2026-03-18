"""Tests for the account setup service."""

from __future__ import annotations

from aiswarm.exchange.providers.aster import AsterExchangeProvider
from aiswarm.execution.account_setup import AccountSetupService
from aiswarm.execution.mcp_gateway import MockMCPGateway


class TestAccountSetupService:
    def test_setup_symbol(self) -> None:
        gateway = MockMCPGateway()
        provider = AsterExchangeProvider(gateway)
        setup = AccountSetupService(provider)

        result = setup.setup_symbol("BTCUSDT", leverage=5, margin_mode="ISOLATED")
        assert result.leverage_set
        assert result.margin_mode_set
        assert setup.is_configured("BTCUSDT")

    def test_setup_records_mcp_calls(self) -> None:
        gateway = MockMCPGateway()
        provider = AsterExchangeProvider(gateway)
        setup = AccountSetupService(provider)

        setup.setup_symbol("BTCUSDT", leverage=3)
        # Should have 2 calls: margin mode + leverage
        assert len(gateway.call_history) == 2
        tools = [c.tool_name for c in gateway.call_history]
        assert "mcp__aster__set_margin_mode" in tools
        assert "mcp__aster__set_leverage" in tools

    def test_setup_all_symbols(self) -> None:
        gateway = MockMCPGateway()
        provider = AsterExchangeProvider(gateway)
        setup = AccountSetupService(provider)

        results = setup.setup_all_symbols(["BTCUSDT", "ETHUSDT"], leverage=2)
        assert len(results) == 2
        assert all(r.leverage_set and r.margin_mode_set for r in results)
        assert setup.configured_symbols == {"BTCUSDT", "ETHUSDT"}

    def test_not_configured_by_default(self) -> None:
        gateway = MockMCPGateway()
        provider = AsterExchangeProvider(gateway)
        setup = AccountSetupService(provider)

        assert not setup.is_configured("BTCUSDT")
        assert len(setup.configured_symbols) == 0
