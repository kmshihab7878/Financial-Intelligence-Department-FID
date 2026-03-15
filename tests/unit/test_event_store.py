"""Tests for the SQLite-backed event store."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from aiswarm.data.event_store import EventStore


class TestEventStore:
    def setup_method(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.db_path = str(Path(self.tmp) / "test_events.db")
        self.store = EventStore(db_path=self.db_path)

    def test_append_and_retrieve(self) -> None:
        event_id = self.store.append("test_type", {"key": "value"}, source="test")
        assert event_id > 0

        events = self.store.get_events(event_type="test_type")
        assert len(events) == 1
        assert events[0]["payload"]["key"] == "value"
        assert events[0]["source"] == "test"

    def test_append_decision(self) -> None:
        decision = {"risk_passed": True, "agent_votes": {"agent1": 0.8}}
        event_id = self.store.append_decision(decision)
        assert event_id > 0

        decisions = self.store.get_decisions(limit=10)
        assert len(decisions) == 1
        assert decisions[0]["payload"]["risk_passed"] is True

    def test_append_order(self) -> None:
        order = {"order_id": "ord_1", "symbol": "BTCUSDT", "side": "buy"}
        event_id = self.store.append_order(order)
        assert event_id > 0

        orders = self.store.get_orders(limit=10)
        assert len(orders) == 1
        assert orders[0]["payload"]["order_id"] == "ord_1"

    def test_append_risk_event(self) -> None:
        risk_event = {"rule": "kill_switch", "severity": "critical"}
        event_id = self.store.append_risk_event(risk_event)
        assert event_id > 0

    def test_append_fill(self) -> None:
        fill = {"order_id": "ord_1", "fill_price": 50000.0}
        event_id = self.store.append_fill(fill)
        assert event_id > 0

    def test_append_reconciliation(self) -> None:
        result = {"passed": True, "mismatches": 0}
        event_id = self.store.append_reconciliation(result)
        assert event_id > 0

    def test_count_events(self) -> None:
        self.store.append("type_a", {"a": 1})
        self.store.append("type_a", {"a": 2})
        self.store.append("type_b", {"b": 1})

        assert self.store.count_events() == 3
        assert self.store.count_events("type_a") == 2
        assert self.store.count_events("type_b") == 1
        assert self.store.count_events("type_c") == 0

    def test_filter_by_timestamp(self) -> None:
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.store.append(
            "evt", {"before": True}, timestamp=datetime(2025, 6, 1, tzinfo=timezone.utc)
        )
        self.store.append(
            "evt", {"after": True}, timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc)
        )

        events = self.store.get_events(event_type="evt", since=ts)
        assert len(events) == 1
        assert events[0]["payload"]["after"] is True

    def test_limit_results(self) -> None:
        for i in range(10):
            self.store.append("bulk", {"i": i})

        events = self.store.get_events(event_type="bulk", limit=3)
        assert len(events) == 3

    def test_save_and_load_checkpoint(self) -> None:
        self.store.save_checkpoint("test_cp", {"state": "running", "nav": 100000})
        loaded = self.store.load_latest_checkpoint("test_cp")
        assert loaded is not None
        assert loaded["payload"]["state"] == "running"
        assert loaded["payload"]["nav"] == 100000

    def test_load_latest_checkpoint_returns_most_recent(self) -> None:
        self.store.save_checkpoint("cp", {"version": 1})
        self.store.save_checkpoint("cp", {"version": 2})
        self.store.save_checkpoint("cp", {"version": 3})

        loaded = self.store.load_latest_checkpoint("cp")
        assert loaded is not None
        assert loaded["payload"]["version"] == 3

    def test_load_nonexistent_checkpoint_returns_none(self) -> None:
        result = self.store.load_latest_checkpoint("nonexistent")
        assert result is None

    def test_portfolio_checkpoint(self) -> None:
        snapshot = {"nav": 50000, "positions": []}
        cp_id = self.store.save_portfolio_checkpoint(snapshot)
        assert cp_id > 0

        loaded = self.store.load_portfolio_checkpoint()
        assert loaded is not None
        assert loaded["payload"]["nav"] == 50000

    def test_memory_checkpoint(self) -> None:
        memory = {"latest_pnl": 0.01, "rolling_drawdown": 0.005}
        cp_id = self.store.save_memory_checkpoint(memory)
        assert cp_id > 0

        loaded = self.store.load_memory_checkpoint()
        assert loaded is not None
        assert loaded["payload"]["latest_pnl"] == 0.01
