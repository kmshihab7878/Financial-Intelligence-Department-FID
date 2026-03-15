from __future__ import annotations

from aiswarm.data.providers.aster import LeverageBracket
from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)


class LeverageGuard:
    """Enforces leverage limits using both configured max and exchange tier data."""

    def breached(self, leverage: float, max_leverage: float) -> bool:
        return leverage > max_leverage

    def validate_against_brackets(
        self,
        notional: float,
        requested_leverage: int,
        brackets: list[LeverageBracket],
    ) -> tuple[bool, int]:
        """Validate leverage against exchange tier limits.

        Returns (is_valid, max_allowed_leverage_for_notional).
        """
        if not brackets:
            return True, requested_leverage

        # Find the bracket that applies to this notional size
        for bracket in sorted(brackets, key=lambda b: b.notional_floor):
            if bracket.notional_floor <= notional <= bracket.notional_cap:
                if requested_leverage > bracket.initial_leverage:
                    logger.warning(
                        "Leverage exceeds exchange tier limit",
                        extra={
                            "extra_json": {
                                "requested": requested_leverage,
                                "max_for_tier": bracket.initial_leverage,
                                "notional": notional,
                            }
                        },
                    )
                    return False, bracket.initial_leverage
                return True, bracket.initial_leverage

        # Notional exceeds all brackets — use lowest leverage
        min_leverage = min(b.initial_leverage for b in brackets)
        return requested_leverage <= min_leverage, min_leverage
