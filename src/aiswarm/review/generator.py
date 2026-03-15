"""Daily review report generator.

Collects data from EventStore, aggregates P&L by mandate,
computes slippage, and builds a DailyReviewReport for operator review.
"""

from __future__ import annotations

from collections import defaultdict

from aiswarm.data.event_store import EventStore
from aiswarm.mandates.registry import MandateRegistry
from aiswarm.orchestration.memory import SharedMemory
from aiswarm.review.models import DailyReviewReport, MandateSummary
from aiswarm.session.models import TradingSession
from aiswarm.utils.ids import new_id
from aiswarm.utils.logging import get_logger
from aiswarm.utils.time import utc_now

logger = get_logger(__name__)


class ReviewGenerator:
    """Generates daily review reports from EventStore data."""

    def __init__(
        self,
        event_store: EventStore,
        mandate_registry: MandateRegistry,
        memory: SharedMemory,
    ) -> None:
        self.event_store = event_store
        self.mandate_registry = mandate_registry
        self.memory = memory

    def generate_daily_report(self, session: TradingSession) -> DailyReviewReport:
        """Build a review report for the given session."""
        start = session.actual_start or session.scheduled_start
        end = session.actual_end or utc_now()

        # Query fills during session
        fills = self.event_store.get_events(event_type="fill", since=start, limit=1000)
        fills_in_session = [f for f in fills if f.get("timestamp", "") <= end.isoformat()]

        # Query reconciliation events
        recon_events = self.event_store.get_events(
            event_type="reconciliation", since=start, limit=100
        )
        recon_mismatches = sum(
            1 for r in recon_events if not r.get("payload", {}).get("passed", True)
        )

        # Query risk events
        risk_events = self.event_store.get_events(event_type="risk_event", since=start, limit=500)

        # Aggregate P&L by mandate
        mandate_pnl: dict[str, float] = defaultdict(float)
        mandate_fills: dict[str, int] = defaultdict(int)
        for fill in fills_in_session:
            payload = fill.get("payload", {})
            mid = payload.get("mandate_id", "unknown")
            pnl = float(payload.get("pnl", 0.0))
            mandate_pnl[mid] += pnl
            mandate_fills[mid] += 1

        # Build per-mandate summaries
        summaries: list[MandateSummary] = []
        all_mandates = self.mandate_registry.list_all()
        mandate_map = {m.mandate_id: m for m in all_mandates}

        # Include mandates that had activity
        seen_mandates = set(mandate_pnl.keys()) | set(mandate_fills.keys())
        # Also include all active mandates
        for m in all_mandates:
            seen_mandates.add(m.mandate_id)

        for mid in sorted(seen_mandates):
            mandate = mandate_map.get(mid)
            tracker = self.memory.mandate_trackers.get(mid)
            summaries.append(
                MandateSummary(
                    mandate_id=mid,
                    strategy=mandate.strategy if mandate else "unknown",
                    fills=mandate_fills.get(mid, 0),
                    gross_pnl=mandate_pnl.get(mid, 0.0),
                    net_pnl=mandate_pnl.get(mid, 0.0),
                    peak_exposure=tracker.gross_exposure if tracker else 0.0,
                    max_drawdown=tracker.drawdown if tracker else 0.0,
                )
            )

        total_pnl = sum(mandate_pnl.values())
        total_fills = len(fills_in_session)

        report = DailyReviewReport(
            report_id=new_id("review"),
            session_id=session.session_id,
            generated_at=utc_now(),
            session_start=start,
            session_end=end,
            mandate_summaries=tuple(summaries),
            total_fills=total_fills,
            total_pnl=total_pnl,
            reconciliation_passed=recon_mismatches == 0,
            reconciliation_mismatches=recon_mismatches,
            risk_events_count=len(risk_events),
        )

        # Persist report event
        self.event_store.append(
            "daily_review",
            report.model_dump(mode="json"),
            source="review_generator",
        )

        logger.info(
            "Daily review report generated",
            extra={
                "extra_json": {
                    "report_id": report.report_id,
                    "session_id": session.session_id,
                    "total_fills": total_fills,
                    "total_pnl": total_pnl,
                }
            },
        )
        return report
