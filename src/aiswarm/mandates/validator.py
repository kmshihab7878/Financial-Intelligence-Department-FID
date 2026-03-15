"""Mandate validator — checks orders against active mandates.

Every order must match an active mandate by strategy and symbol.
The validator also checks mandate-level capital and daily loss limits.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiswarm.mandates.models import Mandate
from aiswarm.mandates.registry import MandateRegistry
from aiswarm.types.orders import Order
from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class MandateValidation:
    """Result of validating an order against mandates."""

    ok: bool
    reason: str
    mandate: Mandate | None


class MandateValidator:
    """Validates orders against active mandates."""

    def __init__(self, registry: MandateRegistry) -> None:
        self.registry = registry

    def validate_order(self, order: Order) -> MandateValidation:
        """Check if an order matches an active mandate.

        Returns (ok=True, mandate) if a matching mandate is found,
        or (ok=False, reason) if no mandate covers this order.
        """
        mandate = self.registry.find_mandate_for_order(order.strategy, order.symbol)
        if mandate is None:
            reason = f"No active mandate for strategy={order.strategy} symbol={order.symbol}"
            logger.warning(
                "Mandate validation failed",
                extra={"extra_json": {"order_id": order.order_id, "reason": reason}},
            )
            return MandateValidation(ok=False, reason=reason, mandate=None)

        logger.info(
            "Mandate validation passed",
            extra={
                "extra_json": {
                    "order_id": order.order_id,
                    "mandate_id": mandate.mandate_id,
                }
            },
        )
        return MandateValidation(ok=True, reason="mandate_matched", mandate=mandate)

    def check_mandate_capital(self, mandate: Mandate, current_exposure: float) -> bool:
        """Check if the mandate has remaining capital budget."""
        return current_exposure < mandate.risk_budget.max_capital

    def check_mandate_daily_loss(self, mandate: Mandate, daily_pnl: float) -> bool:
        """Check if the mandate's daily loss limit has been breached.

        daily_pnl is the absolute P&L value (negative = loss).
        Compares the loss as a fraction of max_capital against max_daily_loss.
        """
        if daily_pnl >= 0:
            return True
        loss_frac = abs(daily_pnl) / mandate.risk_budget.max_capital
        return loss_frac < mandate.risk_budget.max_daily_loss
