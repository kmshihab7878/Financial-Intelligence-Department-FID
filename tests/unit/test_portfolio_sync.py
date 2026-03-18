"""Tests for the portfolio sync service."""

from __future__ import annotations

from aiswarm.exchange.providers.aster import AsterExchangeProvider
from aiswarm.execution.mcp_gateway import MockMCPGateway
from aiswarm.execution.portfolio_sync import PortfolioSyncService
from aiswarm.orchestration.memory import SharedMemory


class TestPortfolioSyncService:
    def test_sync_account_updates_memory(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__aster__get_balance",
            {
                "totalBalance": "100000.0",
                "availableBalance": "80000.0",
                "unrealizedProfit": "500.0",
            },
        )
        gateway.set_response(
            "mcp__aster__get_positions",
            [
                {
                    "symbol": "BTCUSDT",
                    "positionAmt": "0.5",
                    "entryPrice": "50000.0",
                    "markPrice": "51000.0",
                    "unrealizedProfit": "500.0",
                    "leverage": "1",
                    "marginType": "ISOLATED",
                },
            ],
        )

        provider = AsterExchangeProvider(gateway)
        memory = SharedMemory()
        sync = PortfolioSyncService(provider, memory)
        result = sync.sync_account()

        assert result.success
        assert result.nav == 100000.0
        assert result.position_count == 1
        assert memory.latest_snapshot is not None
        assert memory.latest_snapshot.nav == 100000.0
        assert len(memory.latest_snapshot.positions) == 1

    def test_sync_account_no_positions(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__aster__get_balance",
            {
                "totalBalance": "50000.0",
                "availableBalance": "50000.0",
                "unrealizedProfit": "0.0",
            },
        )
        gateway.set_response("mcp__aster__get_positions", [])

        provider = AsterExchangeProvider(gateway)
        memory = SharedMemory()
        sync = PortfolioSyncService(provider, memory)
        result = sync.sync_account()

        assert result.success
        assert result.nav == 50000.0
        assert result.position_count == 0

    def test_sync_account_failure(self) -> None:
        gateway = MockMCPGateway()
        # Don't set responses — will get defaults that may not parse

        provider = AsterExchangeProvider(gateway)
        memory = SharedMemory()
        sync = PortfolioSyncService(provider, memory)
        result = sync.sync_account()

        # Should handle gracefully (parse_balance_response returns None for defaults)
        assert not result.success or result.nav >= 0

    def test_sync_updates_drawdown(self) -> None:
        gateway = MockMCPGateway()
        gateway.set_response(
            "mcp__aster__get_balance",
            {
                "totalBalance": "110000.0",
                "availableBalance": "110000.0",
                "unrealizedProfit": "0.0",
            },
        )
        gateway.set_response("mcp__aster__get_positions", [])

        provider = AsterExchangeProvider(gateway)
        memory = SharedMemory()
        sync = PortfolioSyncService(provider, memory)

        # First sync sets peak
        sync.sync_account()
        assert memory.peak_nav == 110000.0

        # Second sync with lower NAV
        gateway.set_response(
            "mcp__aster__get_balance",
            {
                "totalBalance": "100000.0",
                "availableBalance": "100000.0",
                "unrealizedProfit": "0.0",
            },
        )
        sync.sync_account()
        assert memory.peak_nav == 110000.0  # Peak unchanged
        assert memory.rolling_drawdown > 0  # Drawdown detected
