class Rebalancer:
    def needs_rebalance(self, drift: float, threshold: float = 0.02) -> bool:
        return abs(drift) >= threshold
