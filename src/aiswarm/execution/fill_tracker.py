"""Fill tracker — polls exchange for fills and matches them to internal orders.

Syncs exchange trade history against tracked orders to detect fills,
update order status, and maintain accurate position/P&L state.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiswarm.data.providers.aster_config import normalize_symbol
from aiswarm.exchange.provider import ExchangeProvider
from aiswarm.exchange.types import TradeRecord
from aiswarm.execution.order_store import OrderRecord, OrderStore
from aiswarm.orchestration.memory import SharedMemory
from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class FillSyncResult:
    """Result of a fill sync operation."""

    matched_fills: int
    unmatched_fills: int
    already_filled: int
    total_exchange_trades: int


class FillTracker:
    """Tracks fills from the exchange and reconciles with internal orders."""

    def __init__(
        self,
        provider: ExchangeProvider,
        order_store: OrderStore,
        memory: SharedMemory,
    ) -> None:
        self.provider = provider
        self.order_store = order_store
        self.memory = memory

    def sync_fills(self, symbol: str) -> FillSyncResult:
        """Poll exchange for recent trades and match them to tracked orders.

        For each exchange trade:
          1. Skip if already matched (known exchange ID)
          2. Try to match by exchange order ID -> internal order
          3. Record the fill in OrderStore
          4. Update mandate P&L tracking
        """
        trades = self.provider.get_my_trades(symbol)

        if not trades:
            return FillSyncResult(
                matched_fills=0,
                unmatched_fills=0,
                already_filled=0,
                total_exchange_trades=0,
            )
        matched = 0
        unmatched = 0
        already_filled = 0

        for trade in trades:
            # Check if we already know about this trade
            existing = self.order_store.get_by_exchange_id(trade.trade_id)
            if existing and existing.fill_price is not None:
                already_filled += 1
                continue

            # Try to match by checking open orders' exchange IDs
            record = self._match_trade_to_order(trade)
            if record is None:
                unmatched += 1
                continue

            # Record the fill
            self.order_store.record_fill(
                record.order.order_id,
                fill_price=trade.price,
                fill_quantity=trade.quantity,
            )

            # Update mandate P&L if applicable
            if record.order.mandate_id:
                pnl = trade.realized_pnl if trade.realized_pnl else 0.0
                self.memory.update_mandate_pnl(record.order.mandate_id, pnl)

            matched += 1
            logger.info(
                "Fill matched",
                extra={
                    "extra_json": {
                        "order_id": record.order.order_id,
                        "trade_id": trade.trade_id,
                        "price": trade.price,
                        "quantity": trade.quantity,
                    }
                },
            )

        return FillSyncResult(
            matched_fills=matched,
            unmatched_fills=unmatched,
            already_filled=already_filled,
            total_exchange_trades=len(trades),
        )

    def _match_trade_to_order(self, trade: TradeRecord) -> OrderRecord | None:
        """Match an exchange trade to a tracked order.

        Primary: match by exchange order ID (exact, unambiguous).
        Fallback: match by symbol + side (for trades without order_id linkage).
        """
        # Primary: match by exchange order ID if the trade carries one
        if trade.order_id:
            record = self.order_store.get_by_exchange_id(trade.order_id)
            if record is not None:
                return record

        # Fallback: match by symbol + side across open orders
        for record in self.order_store.get_open_orders():
            if (
                record.exchange_order_id
                and normalize_symbol(record.order.symbol) == normalize_symbol(trade.symbol)
                and record.order.side.value.lower() == trade.side.lower()
            ):
                return record
        return None

    def check_order_status(self, order_id: str, symbol: str) -> str | None:
        """Query the exchange for a specific order's current status."""
        record = self.order_store.get(order_id)
        if record is None or record.exchange_order_id is None:
            return None

        response = self.provider.get_order_status(symbol, record.exchange_order_id)
        return response.get("status")
