"""Portfolio sync service — syncs exchange state into SharedMemory.

Pulls account balances, positions, and P&L from exchange via ExchangeProvider
and updates the in-memory portfolio snapshot used by the risk engine.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiswarm.exchange.provider import ExchangeProvider
from aiswarm.orchestration.memory import SharedMemory
from aiswarm.types.portfolio import PortfolioSnapshot, Position
from aiswarm.utils.logging import get_logger
from aiswarm.utils.time import utc_now

logger = get_logger(__name__)


@dataclass(frozen=True)
class SyncResult:
    """Result of a portfolio sync operation."""

    success: bool
    nav: float
    position_count: int
    message: str


class PortfolioSyncService:
    """Syncs portfolio state from exchange into SharedMemory."""

    def __init__(
        self,
        provider: ExchangeProvider,
        memory: SharedMemory,
    ) -> None:
        self.provider = provider
        self.memory = memory

    def sync_account(self) -> SyncResult:
        """Pull account balance and positions from exchange, update SharedMemory.

        Steps:
          1. Query exchange for balance (get_balance)
          2. Query exchange for positions (get_positions)
          3. Build PortfolioSnapshot
          4. Update SharedMemory.latest_snapshot
        """
        try:
            # Get balance
            balance = self.provider.get_balance()
            if balance is None:
                return SyncResult(
                    success=False,
                    nav=0.0,
                    position_count=0,
                    message="Could not parse balance from exchange",
                )

            # Get positions
            exchange_positions = self.provider.get_positions()

            # Build positions
            internal_positions: list[Position] = []
            gross_exposure = 0.0
            net_exposure = 0.0

            for ep in exchange_positions:
                if abs(ep.quantity) < 1e-10:
                    continue
                market_value = abs(ep.quantity * ep.mark_price)
                gross_exposure += market_value
                signed_value = ep.quantity * ep.mark_price
                if ep.side == "SHORT":
                    signed_value = -signed_value
                net_exposure += signed_value

                internal_positions.append(
                    Position(
                        symbol=ep.symbol,
                        quantity=ep.quantity,
                        avg_price=ep.entry_price,
                        market_price=ep.mark_price,
                        strategy="live",
                    )
                )

            nav = balance.total_balance
            snapshot = PortfolioSnapshot(
                timestamp=utc_now(),
                nav=nav,
                cash=balance.available_balance,
                gross_exposure=gross_exposure / nav if nav > 0 else 0.0,
                net_exposure=net_exposure / nav if nav > 0 else 0.0,
                positions=tuple(internal_positions),
            )

            self.memory.update_snapshot(snapshot)

            logger.info(
                "Portfolio synced from exchange",
                extra={
                    "extra_json": {
                        "nav": nav,
                        "positions": len(internal_positions),
                        "gross_exposure": gross_exposure,
                    }
                },
            )
            return SyncResult(
                success=True,
                nav=nav,
                position_count=len(internal_positions),
                message="Portfolio synced successfully",
            )

        except Exception as e:
            logger.error(
                "Portfolio sync failed",
                extra={"extra_json": {"error": str(e)}},
            )
            return SyncResult(
                success=False,
                nav=0.0,
                position_count=0,
                message=f"Sync failed: {e}",
            )

    def sync_daily_pnl(self) -> float:
        """Compute daily P&L from exchange income records."""
        try:
            records = self.provider.get_income()
            total_pnl = sum(r.amount for r in records if r.income_type == "REALIZED_PNL")

            # Update SharedMemory as fraction of NAV
            if self.memory.latest_snapshot and self.memory.latest_snapshot.nav > 0:
                self.memory.latest_pnl = total_pnl / self.memory.latest_snapshot.nav
            return float(total_pnl)

        except Exception as e:
            logger.error(
                "Daily P&L sync failed",
                extra={"extra_json": {"error": str(e)}},
            )
            return 0.0
