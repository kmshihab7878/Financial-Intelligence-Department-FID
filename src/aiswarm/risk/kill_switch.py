from __future__ import annotations

from aiswarm.data.providers.aster_config import (
    WHITELISTED_SYMBOLS,
)
from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)


class KillSwitch:
    """Emergency trading halt mechanism.

    Triggers when daily P&L fraction breaches the max_daily_loss threshold.
    When triggered in live mode, prepares cancel-all instructions for
    all active symbols across both spot and futures venues.
    """

    def __init__(self, max_daily_loss: float) -> None:
        self.max_daily_loss = max_daily_loss
        self._triggered = False

    def triggered(self, daily_pnl_fraction: float) -> bool:
        if daily_pnl_fraction <= -abs(self.max_daily_loss):
            if not self._triggered:
                logger.critical(
                    "KILL SWITCH TRIGGERED",
                    extra={
                        "extra_json": {
                            "daily_pnl_fraction": daily_pnl_fraction,
                            "threshold": -abs(self.max_daily_loss),
                        }
                    },
                )
                self._triggered = True
            return True
        return False

    @property
    def is_triggered(self) -> bool:
        return self._triggered

    def reset(self) -> None:
        """Reset kill switch (requires manual intervention)."""
        logger.warning("Kill switch manually reset")
        self._triggered = False

    def prepare_emergency_cancels(
        self,
        account_id: str,
        symbols: list[str] | None = None,
    ) -> list[dict[str, str]]:
        """Prepare MCP cancel-all-orders calls for emergency shutdown.

        Returns a list of MCP tool parameter dicts that the caller
        should execute to cancel all open orders.
        """
        targets = symbols or WHITELISTED_SYMBOLS
        cancels: list[dict[str, str]] = []
        for symbol in targets:
            cancels.append(
                {
                    "tool": "mcp__aster__cancel_all_orders",
                    "account_id": account_id,
                    "symbol": symbol,
                }
            )
            cancels.append(
                {
                    "tool": "mcp__aster__cancel_spot_all_orders",
                    "account_id": account_id,
                    "symbol": symbol,
                }
            )
        return cancels
