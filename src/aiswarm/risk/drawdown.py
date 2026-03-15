class DrawdownGuard:
    def breached(self, drawdown: float, max_drawdown: float) -> bool:
        return drawdown >= max_drawdown
