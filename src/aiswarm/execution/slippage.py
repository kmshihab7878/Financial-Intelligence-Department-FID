class SlippageModel:
    def estimate_bps(self, notional: float) -> float:
        return max(1.0, min(25.0, notional / 100000.0))
