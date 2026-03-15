class PortfolioOptimizer:
    def score(self, expected_return: float, risk_penalty: float) -> float:
        return expected_return - risk_penalty
