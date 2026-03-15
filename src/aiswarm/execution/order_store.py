"""Persistent order store — tracks order lifecycle and exchange ID mapping.

Maps internal order IDs to exchange order IDs and tracks all state transitions.
Uses EventStore for persistence.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from aiswarm.data.event_store import EventStore
from aiswarm.types.orders import Order, OrderStatus
from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class OrderRecord:
    """Tracked order with exchange mapping."""

    order: Order
    exchange_order_id: str | None = None
    fill_price: float | None = None
    fill_quantity: float | None = None
    venue: str = "futures"
    submitted_at: float = 0.0


class OrderStore:
    """In-memory order store with EventStore persistence."""

    def __init__(self, event_store: EventStore) -> None:
        self.event_store = event_store
        self._orders: dict[str, OrderRecord] = {}
        self._exchange_map: dict[str, str] = {}  # exchange_id -> internal_id

    def track(self, order: Order, venue: str = "futures") -> OrderRecord:
        """Start tracking an order."""
        record = OrderRecord(order=order, venue=venue)
        self._orders[order.order_id] = record
        self.event_store.append(
            "order_tracked",
            {
                "order_id": order.order_id,
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": order.quantity,
                "notional": order.notional,
                "mandate_id": order.mandate_id,
                "venue": venue,
            },
            source="order_store",
        )
        return record

    def record_submission(self, order_id: str, exchange_order_id: str) -> OrderRecord | None:
        """Record that an order was submitted to the exchange."""
        record = self._orders.get(order_id)
        if record is None:
            return None
        record.exchange_order_id = exchange_order_id
        record.submitted_at = time.monotonic()
        record.order = record.order.model_copy(update={"status": OrderStatus.SUBMITTED})
        self._exchange_map[exchange_order_id] = order_id
        self.event_store.append(
            "order_submitted",
            {
                "order_id": order_id,
                "exchange_order_id": exchange_order_id,
                "symbol": record.order.symbol,
            },
            source="order_store",
        )
        logger.info(
            "Order submitted to exchange",
            extra={
                "extra_json": {
                    "order_id": order_id,
                    "exchange_order_id": exchange_order_id,
                }
            },
        )
        return record

    def record_fill(
        self,
        order_id: str,
        fill_price: float,
        fill_quantity: float,
    ) -> OrderRecord | None:
        """Record that an order was filled."""
        record = self._orders.get(order_id)
        if record is None:
            return None
        record.fill_price = fill_price
        record.fill_quantity = fill_quantity
        record.order = record.order.model_copy(update={"status": OrderStatus.FILLED})
        self.event_store.append(
            "fill",
            {
                "order_id": order_id,
                "exchange_order_id": record.exchange_order_id,
                "symbol": record.order.symbol,
                "side": record.order.side.value,
                "fill_price": fill_price,
                "fill_quantity": fill_quantity,
                "mandate_id": record.order.mandate_id,
                "pnl": 0.0,
            },
            source="order_store",
        )
        logger.info(
            "Order filled",
            extra={
                "extra_json": {
                    "order_id": order_id,
                    "price": fill_price,
                    "quantity": fill_quantity,
                }
            },
        )
        return record

    def record_cancel(self, order_id: str, reason: str = "") -> OrderRecord | None:
        """Record that an order was cancelled."""
        record = self._orders.get(order_id)
        if record is None:
            return None
        record.order = record.order.model_copy(update={"status": OrderStatus.CANCELLED})
        self.event_store.append(
            "order_cancelled",
            {
                "order_id": order_id,
                "exchange_order_id": record.exchange_order_id,
                "reason": reason,
            },
            source="order_store",
        )
        return record

    def get(self, order_id: str) -> OrderRecord | None:
        """Get an order record by internal ID."""
        return self._orders.get(order_id)

    def get_by_exchange_id(self, exchange_order_id: str) -> OrderRecord | None:
        """Look up an order by its exchange order ID."""
        internal_id = self._exchange_map.get(exchange_order_id)
        if internal_id is None:
            return None
        return self._orders.get(internal_id)

    def get_open_orders(self) -> list[OrderRecord]:
        """Get all orders in SUBMITTED status (not yet filled or cancelled)."""
        return [r for r in self._orders.values() if r.order.status == OrderStatus.SUBMITTED]

    def get_stale_orders(self, max_age_seconds: float = 300.0) -> list[OrderRecord]:
        """Get submitted orders older than max_age_seconds."""
        now = time.monotonic()
        return [
            r
            for r in self._orders.values()
            if r.order.status == OrderStatus.SUBMITTED
            and r.submitted_at > 0
            and (now - r.submitted_at) > max_age_seconds
        ]

    def get_all(self) -> list[OrderRecord]:
        """Get all tracked orders."""
        return list(self._orders.values())

    @property
    def known_exchange_ids(self) -> set[str]:
        """All exchange order IDs we know about."""
        return set(self._exchange_map.keys())
