from __future__ import annotations

from aiswarm.risk.limits import verify_risk_token
from aiswarm.types.orders import Order, OrderStatus
from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)


class OMS:
    """Order Management System.

    Validates risk approval tokens before allowing order submission.
    Only orders with valid, non-expired HMAC-signed tokens are accepted.
    """

    def submit(self, order: Order) -> Order:
        if not order.risk_approval_token:
            raise ValueError("risk approval token required before submission")
        if not verify_risk_token(order.risk_approval_token, order.order_id):
            raise ValueError("risk approval token is invalid or expired")
        logger.info(
            "Order submitted",
            extra={"extra_json": {"order_id": order.order_id, "symbol": order.symbol}},
        )
        return order.model_copy(update={"status": OrderStatus.SUBMITTED})
