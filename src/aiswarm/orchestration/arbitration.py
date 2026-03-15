from __future__ import annotations
from collections import defaultdict
from aiswarm.types.market import Signal

MIN_CONFIDENCE = 0.40


class WeightedArbitration:
    def __init__(
        self,
        weights: dict[str, float],
        min_confidence: float = MIN_CONFIDENCE,
    ) -> None:
        self.weights = weights
        self.min_confidence = min_confidence

    def select_signal(self, signals: list[Signal]) -> Signal | None:
        if not signals:
            return None
        eligible = [s for s in signals if s.confidence >= self.min_confidence]
        if not eligible:
            return None
        scores: dict[str, float] = defaultdict(float)
        by_id: dict[str, Signal] = {}
        for signal in eligible:
            weight = self.weights.get(signal.agent_id, 1.0)
            score = weight * signal.confidence * max(signal.expected_return, 0.0)
            score *= max(signal.liquidity_score, 0.01)
            scores[signal.signal_id] += score
            by_id[signal.signal_id] = signal
        best_id = max(scores, key=lambda k: scores[k])
        return by_id[best_id]
