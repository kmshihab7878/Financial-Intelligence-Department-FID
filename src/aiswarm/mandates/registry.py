"""Mandate registry — CRUD + EventStore persistence.

Maintains an in-memory index of mandates with EventStore persistence.
Supports finding the matching mandate for a given order based on
strategy and symbol.
"""

from __future__ import annotations

from aiswarm.data.event_store import EventStore
from aiswarm.mandates.models import Mandate, MandateRiskBudget, MandateStatus
from aiswarm.utils.logging import get_logger
from aiswarm.utils.time import utc_now

logger = get_logger(__name__)


class MandateRegistry:
    """In-memory mandate store backed by EventStore for durability."""

    def __init__(self, event_store: EventStore) -> None:
        self.event_store = event_store
        self._mandates: dict[str, Mandate] = {}

    def create(
        self,
        mandate_id: str,
        strategy: str,
        symbols: tuple[str, ...],
        risk_budget: MandateRiskBudget,
        created_by: str = "system",
        notes: str = "",
    ) -> Mandate:
        """Create and register a new mandate."""
        if mandate_id in self._mandates:
            raise ValueError(f"Mandate {mandate_id} already exists")
        mandate = Mandate(
            mandate_id=mandate_id,
            strategy=strategy,
            symbols=symbols,
            risk_budget=risk_budget,
            created_at=utc_now(),
            created_by=created_by,
            notes=notes,
        )
        self._mandates[mandate_id] = mandate
        self.event_store.append(
            "mandate",
            {"action": "created", "mandate": mandate.model_dump(mode="json")},
            source="mandate_registry",
        )
        logger.info(
            "Mandate created",
            extra={
                "extra_json": {
                    "mandate_id": mandate.mandate_id,
                    "strategy": mandate.strategy,
                    "symbols": list(mandate.symbols),
                }
            },
        )
        return mandate

    def get(self, mandate_id: str) -> Mandate | None:
        """Get a mandate by ID."""
        return self._mandates.get(mandate_id)

    def list_active(self) -> list[Mandate]:
        """List all active mandates."""
        return [m for m in self._mandates.values() if m.status == MandateStatus.ACTIVE]

    def list_all(self) -> list[Mandate]:
        """List all mandates regardless of status."""
        return list(self._mandates.values())

    def update_status(self, mandate_id: str, new_status: MandateStatus) -> Mandate | None:
        """Update mandate status (pause, revoke, etc.)."""
        mandate = self._mandates.get(mandate_id)
        if mandate is None:
            return None
        updated = mandate.model_copy(update={"status": new_status, "updated_at": utc_now()})
        self._mandates[mandate_id] = updated
        self.event_store.append(
            "mandate",
            {
                "action": "status_changed",
                "mandate_id": mandate_id,
                "old_status": mandate.status.value,
                "new_status": new_status.value,
            },
            source="mandate_registry",
        )
        logger.info(
            "Mandate status updated",
            extra={
                "extra_json": {
                    "mandate_id": mandate_id,
                    "old_status": mandate.status.value,
                    "new_status": new_status.value,
                }
            },
        )
        return updated

    def revoke(self, mandate_id: str) -> Mandate | None:
        """Revoke a mandate — permanent deactivation."""
        return self.update_status(mandate_id, MandateStatus.REVOKED)

    def find_mandate_for_order(self, strategy: str, symbol: str) -> Mandate | None:
        """Find an active mandate that matches the given strategy and symbol."""
        for mandate in self.list_active():
            if mandate.strategy == strategy and symbol in mandate.symbols:
                return mandate
        return None
