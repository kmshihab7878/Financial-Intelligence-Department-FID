from __future__ import annotations

from aiswarm.quant.kelly import half_kelly
from aiswarm.types.market import Signal
from aiswarm.types.orders import Order, Side
from aiswarm.types.portfolio import PortfolioSnapshot
from aiswarm.utils.ids import new_id
from aiswarm.utils.time import utc_now


class PortfolioAllocator:
    def __init__(
        self,
        target_weight: float = 0.02,
        use_kelly: bool = False,
        max_kelly_weight: float = 0.05,
    ) -> None:
        self.target_weight = target_weight
        self.use_kelly = use_kelly
        self.max_kelly_weight = max_kelly_weight

    def order_from_signal(self, signal: Signal, snapshot: PortfolioSnapshot | None) -> Order:
        nav = snapshot.nav if snapshot else 1_000_000.0
        weight = self._compute_weight(signal)
        notional = max(nav * weight * signal.confidence, 100.0)
        price_proxy = signal.reference_price if signal.reference_price > 0 else 100.0
        quantity = round(notional / price_proxy, 4)
        side = Side.BUY if signal.direction >= 0 else Side.SELL
        return Order(
            order_id=new_id("ord"),
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            side=side,
            quantity=quantity,
            limit_price=None,
            notional=notional,
            strategy=signal.strategy,
            thesis=signal.thesis,
            created_at=utc_now(),
        )

    def _compute_weight(self, signal: Signal) -> float:
        """Compute position weight. Uses half-Kelly if enabled, else target_weight."""
        if not self.use_kelly:
            return self.target_weight
        # Derive win_prob from confidence, payout from expected_return
        win_prob = signal.confidence
        payout_ratio = 1.0 + max(signal.expected_return, 0.0) * 10
        kelly_w = half_kelly(win_prob, payout_ratio)
        if kelly_w <= 0:
            return self.target_weight
        return min(kelly_w, self.max_kelly_weight)
