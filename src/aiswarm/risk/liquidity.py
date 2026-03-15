from __future__ import annotations

from aiswarm.data.providers.aster import OrderBook
from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)


class LiquidityGuard:
    """Enforces minimum liquidity requirements."""

    def breached(self, liquidity_score: float, minimum: float) -> bool:
        return liquidity_score < minimum

    def check_orderbook_depth(
        self,
        orderbook: OrderBook,
        notional: float,
        max_depth_consumption: float = 0.10,
    ) -> tuple[bool, float]:
        """Check if an order would consume too much visible order book depth.

        Args:
            orderbook: Current order book snapshot.
            notional: Order notional value.
            max_depth_consumption: Max fraction of visible depth the order may consume.

        Returns:
            (is_safe, consumption_ratio)
        """
        depth = min(orderbook.bid_depth, orderbook.ask_depth)
        if depth <= 0:
            logger.warning(
                "Empty order book — blocking order",
                extra={"extra_json": {"symbol": orderbook.symbol}},
            )
            return False, 1.0

        consumption = notional / depth
        if consumption > max_depth_consumption:
            logger.warning(
                "Order would consume too much order book depth",
                extra={
                    "extra_json": {
                        "symbol": orderbook.symbol,
                        "consumption": f"{consumption:.4f}",
                        "max": f"{max_depth_consumption:.4f}",
                        "notional": notional,
                        "depth": depth,
                    }
                },
            )
            return False, consumption
        return True, consumption
