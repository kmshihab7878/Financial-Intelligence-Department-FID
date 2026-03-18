"""Live order executor — submits orders to exchange via ExchangeProvider.

Bridges the gap between the OMS (token validation) and actual exchange execution.
Uses the ExchangeProvider interface for exchange-agnostic order submission.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiswarm.exchange.provider import ExchangeProvider
from aiswarm.execution.aster_executor import AsterExecutor, ExecutionMode
from aiswarm.execution.order_store import OrderStore
from aiswarm.types.orders import Order, Side
from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class SubmissionResult:
    """Result of submitting an order to the exchange."""

    success: bool
    order_id: str
    exchange_order_id: str | None
    message: str


class LiveOrderExecutor:
    """Submits orders to exchange via ExchangeProvider and tracks their lifecycle.

    Wraps AsterExecutor (mode/validation) + ExchangeProvider (exchange calls)
    + OrderStore (persistence) into a single execution service.
    """

    def __init__(
        self,
        executor: AsterExecutor,
        provider: ExchangeProvider,
        order_store: OrderStore,
        default_venue: str = "futures",
    ) -> None:
        self.executor = executor
        self.provider = provider
        self.order_store = order_store
        self.default_venue = default_venue

    def submit_order(
        self,
        order: Order,
        venue: str | None = None,
    ) -> SubmissionResult:
        """Submit an order to the exchange.

        1. Track the order in OrderStore
        2. Call ExchangeProvider.place_order()
        3. Record the exchange order ID
        """
        venue = venue or self.default_venue

        # Paper mode: simulate fill, don't call exchange
        if self.executor.mode == ExecutionMode.PAPER:
            return self._handle_paper(order)

        # Track the order
        self.order_store.track(order, venue=venue)

        # Submit via provider
        try:
            side_str = "BUY" if order.side == Side.BUY else "SELL"
            order_type = "LIMIT" if order.limit_price else "MARKET"

            response = self.provider.place_order(
                symbol=order.symbol,
                side=side_str,
                quantity=order.quantity,
                order_type=order_type,
                price=order.limit_price,
                venue=venue,
            )
            exchange_order_id = response.get("orderId", "")

            if not exchange_order_id:
                logger.error(
                    "Exchange returned no order ID",
                    extra={"extra_json": {"order_id": order.order_id, "response": response}},
                )
                return SubmissionResult(
                    success=False,
                    order_id=order.order_id,
                    exchange_order_id=None,
                    message=f"Exchange returned no order ID: {response}",
                )

            self.order_store.record_submission(order.order_id, exchange_order_id)

            logger.info(
                "Order submitted to exchange",
                extra={
                    "extra_json": {
                        "order_id": order.order_id,
                        "exchange_order_id": exchange_order_id,
                        "symbol": order.symbol,
                    }
                },
            )
            return SubmissionResult(
                success=True,
                order_id=order.order_id,
                exchange_order_id=exchange_order_id,
                message="Order submitted successfully",
            )

        except Exception as e:
            logger.error(
                "Order submission failed",
                extra={"extra_json": {"order_id": order.order_id, "error": str(e)}},
            )
            self.order_store.record_cancel(order.order_id, reason=f"submission_failed: {e}")
            return SubmissionResult(
                success=False,
                order_id=order.order_id,
                exchange_order_id=None,
                message=f"Submission failed: {e}",
            )

    def cancel_order(
        self,
        order_id: str,
        venue: str | None = None,
    ) -> SubmissionResult:
        """Cancel an order on the exchange."""
        venue = venue or self.default_venue
        record = self.order_store.get(order_id)
        if record is None:
            return SubmissionResult(
                success=False,
                order_id=order_id,
                exchange_order_id=None,
                message="Order not found in store",
            )
        if record.exchange_order_id is None:
            return SubmissionResult(
                success=False,
                order_id=order_id,
                exchange_order_id=None,
                message="Order has no exchange ID (not yet submitted?)",
            )

        try:
            self.provider.cancel_order(
                symbol=record.order.symbol,
                order_id=record.exchange_order_id,
                venue=venue,
            )
            self.order_store.record_cancel(order_id, reason="operator_cancel")
            return SubmissionResult(
                success=True,
                order_id=order_id,
                exchange_order_id=record.exchange_order_id,
                message="Order cancelled",
            )
        except Exception as e:
            return SubmissionResult(
                success=False,
                order_id=order_id,
                exchange_order_id=record.exchange_order_id,
                message=f"Cancel failed: {e}",
            )

    def cancel_for_symbols(self, symbols: list[str]) -> list[SubmissionResult]:
        """Surgical cancel — cancel orders only for the specified symbols.

        Unlike ``cancel_all`` which is a nuclear option across all whitelisted
        symbols, this method targets specific symbols (e.g. those flagged by
        reconciliation mismatches).
        """
        results: list[SubmissionResult] = []

        for symbol in symbols:
            for venue in ("futures", "spot"):
                try:
                    self.provider.cancel_all_orders(symbol, venue)
                    results.append(
                        SubmissionResult(
                            success=True,
                            order_id=f"cancel_symbol_{symbol}_{venue}",
                            exchange_order_id=None,
                            message=f"Surgical cancel {venue} for {symbol}",
                        )
                    )
                except Exception as e:
                    results.append(
                        SubmissionResult(
                            success=False,
                            order_id=f"cancel_symbol_{symbol}_{venue}",
                            exchange_order_id=None,
                            message=f"Surgical cancel failed: {e}",
                        )
                    )

            # Mark only this symbol's open orders as cancelled
            for record in self.order_store.get_open_orders_for_symbol(symbol):
                self.order_store.record_cancel(
                    record.order.order_id,
                    reason=f"surgical_reconciliation_cancel:{symbol}",
                )

        logger.info(
            "Surgical cancel completed",
            extra={
                "extra_json": {
                    "symbols": symbols,
                    "results_count": len(results),
                }
            },
        )
        return results

    def cancel_all(self, symbols: list[str] | None = None) -> list[SubmissionResult]:
        """Emergency cancel all orders across symbols."""
        from aiswarm.data.providers.aster_config import WHITELISTED_SYMBOLS

        symbols = symbols or WHITELISTED_SYMBOLS
        results: list[SubmissionResult] = []

        for symbol in symbols:
            for venue in ("futures", "spot"):
                try:
                    self.provider.cancel_all_orders(symbol, venue)
                    results.append(
                        SubmissionResult(
                            success=True,
                            order_id=f"cancel_all_{symbol}_{venue}",
                            exchange_order_id=None,
                            message=f"Cancel all {venue} for {symbol}",
                        )
                    )
                except Exception as e:
                    results.append(
                        SubmissionResult(
                            success=False,
                            order_id=f"cancel_all_{symbol}_{venue}",
                            exchange_order_id=None,
                            message=f"Cancel all failed: {e}",
                        )
                    )

        # Mark all tracked open orders as cancelled
        for record in self.order_store.get_open_orders():
            self.order_store.record_cancel(record.order.order_id, reason="emergency_cancel_all")

        return results

    def _handle_paper(self, order: Order) -> SubmissionResult:
        """Handle paper mode: simulate fill immediately."""
        self.order_store.track(order, venue="paper")
        result = self.executor.simulate_paper_fill(order, current_price=0.0)
        exchange_id = result.exchange_order_id or f"paper_{order.order_id}"
        self.order_store.record_submission(order.order_id, exchange_id)
        if result.fill_price is not None and result.fill_quantity is not None:
            self.order_store.record_fill(order.order_id, result.fill_price, result.fill_quantity)
        return SubmissionResult(
            success=True,
            order_id=order.order_id,
            exchange_order_id=exchange_id,
            message="Paper fill simulated",
        )
