"""Tests for the autonomous trading loop."""

from __future__ import annotations

import tempfile
from datetime import timedelta
from typing import Any

from aiswarm.agents.base import Agent
from aiswarm.data.event_store import EventStore
from aiswarm.execution.account_setup import AccountSetupService
from aiswarm.execution.aster_executor import AsterExecutor, ExecutionMode
from aiswarm.execution.fill_tracker import FillTracker
from aiswarm.execution.live_executor import LiveOrderExecutor
from aiswarm.execution.mcp_gateway import MockMCPGateway
from aiswarm.execution.order_store import OrderStore
from aiswarm.execution.portfolio_sync import PortfolioSyncService
from aiswarm.loop.config import LoopConfig
from aiswarm.loop.market_data import MarketDataService
from aiswarm.loop.trading_loop import CycleResult, LoopState, TradingLoop
from aiswarm.monitoring.reconciliation import PositionReconciler, ReconciliationLoop
from aiswarm.orchestration.coordinator import Coordinator
from aiswarm.orchestration.memory import SharedMemory
from aiswarm.resilience.shutdown import GracefulShutdown
from aiswarm.risk.limits import RiskEngine
from aiswarm.session.manager import SessionManager
from aiswarm.types.market import MarketRegime, Signal
from aiswarm.utils.ids import new_id
from aiswarm.utils.time import utc_now


def _make_event_store() -> EventStore:
    return EventStore(tempfile.mktemp(suffix=".db"))


class StubAgent(Agent):
    """Agent that returns a configurable signal."""

    def __init__(self, signal: Signal | None = None) -> None:
        super().__init__(agent_id="stub_agent", cluster="test")
        self._signal = signal

    def analyze(self, context: dict[str, Any]) -> dict[str, Any]:
        return {"signal": self._signal}

    def propose(self, context: dict[str, Any]) -> dict[str, Any]:
        return self.analyze(context)

    def validate(self, context: dict[str, Any]) -> bool:
        return True


def _make_signal(symbol: str = "BTCUSDT") -> Signal:
    return Signal(
        signal_id=new_id("sig"),
        agent_id="stub_agent",
        symbol=symbol,
        strategy="momentum",
        thesis="test signal thesis",
        direction=1,
        confidence=0.8,
        expected_return=0.01,
        horizon_minutes=60,
        liquidity_score=0.9,
        regime=MarketRegime.RISK_ON,
        created_at=utc_now(),
    )


def _build_loop(
    agents: list[Agent] | None = None,
    config: LoopConfig | None = None,
    session_active: bool = True,
) -> TradingLoop:
    """Build a TradingLoop with all dependencies wired for testing."""
    es = _make_event_store()
    gateway = MockMCPGateway()

    # Setup balance/positions for portfolio sync
    gateway.set_response(
        "mcp__aster__get_balance",
        {
            "totalBalance": "100000.0",
            "availableBalance": "90000.0",
            "unrealizedProfit": "0.0",
        },
    )
    gateway.set_response("mcp__aster__get_positions", [])

    memory = SharedMemory()
    executor = AsterExecutor(mode=ExecutionMode.PAPER)
    store = OrderStore(es)
    live_executor = LiveOrderExecutor(executor, gateway, store)
    fill_tracker = FillTracker(gateway, store, memory)
    portfolio_sync = PortfolioSyncService(gateway, memory)
    account_setup = AccountSetupService(executor, gateway)
    market_data = MarketDataService(gateway)

    # Session manager — optionally pre-activate
    session_mgr = SessionManager(es)
    if session_active:
        now = utc_now()
        session_mgr.start_session(
            scheduled_start=now - timedelta(minutes=1),
            scheduled_end=now + timedelta(hours=8),
        )
        session_mgr.approve_session(operator="test")
        session_mgr.activate_session()

    # Risk engine with generous limits
    risk_engine = RiskEngine(
        max_position_weight=0.5,
        max_gross_exposure=2.0,
        max_daily_loss=0.10,
        max_rolling_drawdown=0.10,
        max_leverage=5.0,
        min_liquidity_score=0.0,
    )

    # Coordinator
    from aiswarm.orchestration.arbitration import WeightedArbitration
    from aiswarm.portfolio.allocator import PortfolioAllocator

    arbitration = WeightedArbitration(weights={"stub_agent": 1.0})
    allocator = PortfolioAllocator()
    coordinator = Coordinator(
        arbitration=arbitration,
        allocator=allocator,
        risk_engine=risk_engine,
        memory=memory,
        decision_log_path=tempfile.mktemp(suffix=".jsonl"),
        session_manager=session_mgr,
    )

    # Reconciliation
    reconciler = PositionReconciler()
    recon_loop = ReconciliationLoop(
        reconciler=reconciler,
        event_store=es,
        pause_callback=lambda: None,
    )

    # Shutdown — not installed (no signal handlers in tests)
    shutdown = GracefulShutdown()

    loop = TradingLoop(
        coordinator=coordinator,
        live_executor=live_executor,
        fill_tracker=fill_tracker,
        portfolio_sync=portfolio_sync,
        account_setup=account_setup,
        session_manager=session_mgr,
        reconciliation_loop=recon_loop,
        shutdown=shutdown,
        gateway=gateway,
        memory=memory,
        agents=agents or [StubAgent()],
        market_data=market_data,
        config=config or LoopConfig(symbols=("BTCUSDT",)),
    )
    return loop


class TestTradingLoop:
    def test_single_cycle_no_signal(self) -> None:
        """Cycle with no signal produces no order."""
        loop = _build_loop(agents=[StubAgent(signal=None)])
        result = loop._run_cycle()

        assert result.cycle_number == 1
        assert result.signals_generated == 0
        assert not result.order_submitted
        assert result.duration_seconds >= 0

    def test_single_cycle_with_signal(self) -> None:
        """Cycle with a signal goes through full pipeline."""
        signal = _make_signal()
        loop = _build_loop(agents=[StubAgent(signal=signal)])

        # Do initial portfolio sync for coordinator to have a snapshot
        loop.portfolio_sync.sync_account()
        loop.state.last_portfolio_sync = 0  # Force sync

        result = loop._run_cycle()

        assert result.cycle_number == 1
        assert result.signals_generated == 1
        # In paper mode, order should be submitted successfully
        assert result.order_submitted

    def test_cycle_increments_counter(self) -> None:
        loop = _build_loop()
        loop._run_cycle()
        loop._run_cycle()
        assert loop.state.cycle_count == 2

    def test_loop_state_defaults(self) -> None:
        state = LoopState()
        assert state.cycle_count == 0
        assert state.consecutive_errors == 0
        assert not state.halted
        assert state.halt_reason == ""

    def test_halt_sets_state(self) -> None:
        loop = _build_loop()
        loop._halt("test reason")
        assert loop.state.halted
        assert loop.state.halt_reason == "test reason"

    def test_run_stops_on_shutdown(self) -> None:
        """Loop exits when shutdown.is_running becomes False."""
        loop = _build_loop()
        # Immediately trigger shutdown
        loop.shutdown.initiate_shutdown("test")
        state = loop.run()
        assert state.cycle_count == 0  # No cycles run

    def test_run_stops_on_halt(self) -> None:
        """Loop exits when halted."""
        loop = _build_loop()
        loop.state.halted = True
        loop.state.halt_reason = "pre-halted"
        state = loop.run()
        assert state.halted

    def test_session_gate_blocks_cycle(self) -> None:
        """When session is not active, loop waits instead of running cycles."""
        loop = _build_loop(session_active=False)
        # Shutdown immediately so the wait doesn't block
        loop.shutdown.initiate_shutdown("test")
        state = loop.run()
        assert state.cycle_count == 0

    def test_consecutive_errors_halt(self) -> None:
        """Loop halts after max consecutive errors."""
        config = LoopConfig(
            symbols=("BTCUSDT",),
            max_consecutive_errors=2,
            cycle_interval=0.01,
        )
        loop = _build_loop(config=config)

        # Override _run_cycle to always raise, simulating critical failures
        def failing_cycle() -> CycleResult:
            raise RuntimeError("cycle boom")

        loop._run_cycle = failing_cycle  # type: ignore[assignment]

        state = loop.run()
        assert state.halted
        assert state.consecutive_errors >= 2

    def test_multiple_symbols(self) -> None:
        """Loop processes multiple symbols."""
        config = LoopConfig(symbols=("BTCUSDT", "ETHUSDT"))
        loop = _build_loop(config=config)
        loop._run_cycle()

        # Should have fetched data for both symbols
        tools = [c.tool_name for c in loop.gateway.call_history]  # type: ignore[union-attr]
        kline_calls = [t for t in tools if t == "mcp__aster__get_klines"]
        assert len(kline_calls) >= 2

    def test_fill_sync_respects_interval(self) -> None:
        """Fill sync only runs when interval has elapsed."""
        import time

        config = LoopConfig(
            symbols=("BTCUSDT",),
            fill_sync_interval=9999.0,  # Very long interval
        )
        loop = _build_loop(config=config)

        # Force first sync by setting last_fill_sync far in the past
        loop.state.last_fill_sync = time.monotonic() - 99999.0
        loop._run_cycle()

        # After first cycle, last_fill_sync is updated to recent time
        assert loop.state.last_fill_sync > 0

        # Second cycle should NOT run fill sync (interval not elapsed)
        saved = loop.state.last_fill_sync
        loop._run_cycle()
        # last_fill_sync should NOT be updated since interval hasn't elapsed
        assert loop.state.last_fill_sync == saved

    def test_setup_account_called(self) -> None:
        """Account setup runs during loop initialization."""
        loop = _build_loop()
        # _setup_account is called during run(), but we can test it directly
        loop._setup_account()
        assert loop.account_setup.is_configured("BTCUSDT")

    def test_cycle_result_structure(self) -> None:
        result = CycleResult(
            cycle_number=1,
            signals_generated=2,
            order_submitted=True,
            fills_matched=1,
            reconciliation_passed=True,
            errors=("err1",),
            duration_seconds=0.5,
        )
        assert result.cycle_number == 1
        assert result.order_submitted
        assert result.errors == ("err1",)

    def test_process_symbol_returns_signals(self) -> None:
        signal = _make_signal("BTCUSDT")
        loop = _build_loop(agents=[StubAgent(signal=signal)])
        signals = loop._process_symbol("BTCUSDT")
        assert len(signals) == 1
        assert signals[0].symbol == "BTCUSDT"

    def test_process_symbol_no_signal(self) -> None:
        loop = _build_loop(agents=[StubAgent(signal=None)])
        signals = loop._process_symbol("BTCUSDT")
        assert len(signals) == 0

    def test_emit_heartbeat(self) -> None:
        """Heartbeat doesn't raise."""
        loop = _build_loop()
        loop._emit_heartbeat()  # Should not raise
