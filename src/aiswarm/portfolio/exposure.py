from __future__ import annotations
from aiswarm.types.orders import Order
from aiswarm.types.portfolio import PortfolioSnapshot


class ExposureManager:
    def __init__(self, max_position_weight: float, max_gross_exposure: float) -> None:
        self.max_position_weight = max_position_weight
        self.max_gross_exposure = max_gross_exposure

    def check_order(self, order: Order, snapshot: PortfolioSnapshot | None) -> tuple[bool, str]:
        nav = snapshot.nav if snapshot else 1_000_000.0
        weight = order.notional / nav
        if weight > self.max_position_weight:
            return (
                False,
                f"position_weight {weight:.4f} exceeds limit {self.max_position_weight:.4f}",
            )
        gross = (snapshot.gross_exposure if snapshot else 0.0) + weight
        if gross > self.max_gross_exposure:
            return False, f"gross_exposure {gross:.4f} exceeds limit {self.max_gross_exposure:.4f}"
        return True, "ok"
