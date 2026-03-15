"""Bootstrap — loads configuration and wires all components into a TradingLoop.

Reads YAML config files and constructs the full component graph:
  config → agents → coordinator → executor → loop

Usage:
    from aiswarm.bootstrap import bootstrap_from_config
    loop = bootstrap_from_config("config/")
    loop.run()
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from aiswarm.agents.base import Agent
from aiswarm.agents.market_intelligence.funding_rate_agent import FundingRateAgent
from aiswarm.agents.strategy.momentum_agent import MomentumAgent
from aiswarm.data.event_store import EventStore
from aiswarm.data.providers.aster_config import AsterConfig
from aiswarm.execution.account_setup import AccountSetupService
from aiswarm.execution.aster_executor import AsterExecutor, ExecutionMode
from aiswarm.execution.fill_tracker import FillTracker
from aiswarm.execution.live_executor import LiveOrderExecutor
from aiswarm.execution.mcp_gateway import AsterMCPGateway, MCPGateway, MockMCPGateway
from aiswarm.execution.order_store import OrderStore
from aiswarm.execution.portfolio_sync import PortfolioSyncService
from aiswarm.loop.config import LoopConfig
from aiswarm.loop.market_data import MarketDataService
from aiswarm.loop.trading_loop import TradingLoop
from aiswarm.mandates.models import MandateRiskBudget
from aiswarm.mandates.registry import MandateRegistry
from aiswarm.mandates.validator import MandateValidator
from aiswarm.monitoring.alerts import AlertDispatcher
from aiswarm.monitoring.reconciliation import PositionReconciler, ReconciliationLoop
from aiswarm.orchestration.arbitration import WeightedArbitration
from aiswarm.orchestration.coordinator import Coordinator
from aiswarm.orchestration.memory import SharedMemory
from aiswarm.portfolio.allocator import PortfolioAllocator
from aiswarm.resilience.shutdown import GracefulShutdown
from aiswarm.risk.limits import RiskEngine
from aiswarm.session.manager import SessionManager
from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML file, returning empty dict if not found."""
    path = Path(path)
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_config(config_dir: str | Path) -> dict[str, Any]:
    """Load and merge all YAML config files from a directory."""
    config_dir = Path(config_dir)
    merged: dict[str, Any] = {}

    for name in ("base", "risk", "execution", "mandates", "portfolio", "monitoring"):
        path = config_dir / f"{name}.yaml"
        data = load_yaml(path)
        merged.update(data)

    # Environment-specific overrides (paper.yaml or live.yaml)
    env = os.environ.get("AIS_ENVIRONMENT", "paper")
    env_path = config_dir / f"{env}.yaml"
    if env_path.exists():
        merged.update(load_yaml(env_path))

    return merged


def build_agents(config: dict[str, Any]) -> list[Agent]:
    """Build agent instances from configuration."""
    agents: list[Agent] = [
        MomentumAgent(),
        FundingRateAgent(),
    ]
    return agents


def build_risk_engine(config: dict[str, Any]) -> RiskEngine:
    """Build RiskEngine from risk config section."""
    risk = config.get("risk", {})
    return RiskEngine(
        max_position_weight=risk.get("max_position_weight", 0.05),
        max_gross_exposure=risk.get("max_gross_exposure", 1.0),
        max_daily_loss=risk.get("max_daily_loss", 0.02),
        max_rolling_drawdown=risk.get("max_rolling_drawdown", 0.05),
        max_leverage=risk.get("max_leverage", 1.0),
        min_liquidity_score=risk.get("min_liquidity_score", 0.50),
    )


def build_loop_config(config: dict[str, Any]) -> LoopConfig:
    """Build LoopConfig from merged configuration."""
    loop_cfg = config.get("loop", {})
    symbols = config.get("symbols", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    return LoopConfig(
        cycle_interval=loop_cfg.get("cycle_interval", 60.0),
        portfolio_sync_interval=loop_cfg.get("portfolio_sync_interval", 30.0),
        fill_sync_interval=loop_cfg.get("fill_sync_interval", 15.0),
        reconciliation_interval=loop_cfg.get("reconciliation_interval", 60.0),
        klines_interval=loop_cfg.get("klines_interval", "1h"),
        klines_limit=loop_cfg.get("klines_limit", 100),
        symbols=tuple(symbols),
        default_leverage=config.get("execution", {}).get("default_leverage", 1),
        default_margin_mode=config.get("execution", {}).get("default_margin_mode", "ISOLATED"),
        max_consecutive_errors=loop_cfg.get("max_consecutive_errors", 5),
        heartbeat_interval=loop_cfg.get("heartbeat_interval", 10.0),
    )


def register_mandates(registry: MandateRegistry, config: dict[str, Any]) -> None:
    """Register mandates from config into the registry."""
    mandates = config.get("mandates", [])
    for m in mandates:
        budget_data = m.get("risk_budget", {})
        budget = MandateRiskBudget(
            max_capital=budget_data.get("max_capital", 10000.0),
            max_daily_loss=budget_data.get("max_daily_loss", 0.02),
            max_drawdown=budget_data.get("max_drawdown", 0.05),
            max_open_orders=budget_data.get("max_open_orders", 3),
            max_position_notional=budget_data.get("max_position_notional", 5000.0),
        )
        registry.create(
            mandate_id=m["mandate_id"],
            strategy=m["strategy"],
            symbols=m.get("symbols", []),
            risk_budget=budget,
        )


def validate_mandate_strategies(
    registry: MandateRegistry,
    agents: list[Agent],
) -> None:
    """Validate that every mandate's strategy matches a registered agent strategy.

    Raises RuntimeError if any mandate references a strategy that no agent produces.
    """
    agent_strategies: set[str] = set()
    for agent in agents:
        # Each agent type has a known strategy string
        if hasattr(agent, "analyze"):
            agent_strategies.add(_infer_agent_strategy(agent))

    for mandate in registry.list_all():
        if mandate.strategy not in agent_strategies:
            raise RuntimeError(
                f"Mandate '{mandate.mandate_id}' references strategy "
                f"'{mandate.strategy}' but no registered agent produces it. "
                f"Known strategies: {sorted(agent_strategies)}"
            )
    logger.info(
        "Mandate strategy validation passed",
        extra={"extra_json": {"strategies": sorted(agent_strategies)}},
    )


def _infer_agent_strategy(agent: Agent) -> str:
    """Infer the strategy string an agent uses in its Signal output."""
    if isinstance(agent, MomentumAgent):
        return "momentum_ma_crossover"
    if isinstance(agent, FundingRateAgent):
        return "funding_rate_contrarian"
    return agent.agent_id


def resolve_execution_mode(config: dict[str, Any]) -> ExecutionMode:
    """Determine execution mode from config and environment."""
    env_mode = os.environ.get("AIS_EXECUTION_MODE", "").lower()
    if env_mode == "live":
        return ExecutionMode.LIVE
    if env_mode == "shadow":
        return ExecutionMode.SHADOW

    cfg_mode = config.get("mode", config.get("environment", "paper"))
    if cfg_mode == "live":
        return ExecutionMode.LIVE
    if cfg_mode == "shadow":
        return ExecutionMode.SHADOW
    return ExecutionMode.PAPER


def bootstrap_from_config(
    config_dir: str | Path = "config/",
    gateway: MCPGateway | None = None,
    db_path: str | None = None,
) -> TradingLoop:
    """Build a fully wired TradingLoop from YAML configuration.

    Args:
        config_dir: Path to config directory containing YAML files.
        gateway: Optional MCPGateway override (uses MockMCPGateway if None).
        db_path: Optional EventStore database path.

    Returns:
        A ready-to-run TradingLoop instance.
    """
    config = load_config(config_dir)
    logger.info(
        "Configuration loaded",
        extra={"extra_json": {"config_dir": str(config_dir)}},
    )

    # Core infrastructure
    db_path = db_path or os.environ.get("AIS_DB_PATH", str(Path("data") / "ais_events.db"))
    event_store = EventStore(db_path)
    memory = SharedMemory()

    # Execution mode (resolved before gateway so gateway selection can depend on it)
    mode = resolve_execution_mode(config)
    logger.info("Execution mode", extra={"extra_json": {"mode": mode.value}})

    gateway = gateway or _build_gateway(mode)

    # Executor stack
    aster_config = AsterConfig.from_env() if mode == ExecutionMode.LIVE else None
    executor = AsterExecutor(config=aster_config, mode=mode)
    order_store = OrderStore(event_store)
    live_executor = LiveOrderExecutor(executor, gateway, order_store)

    # Services
    fill_tracker = FillTracker(gateway, order_store, memory)
    portfolio_sync = PortfolioSyncService(gateway, memory)
    account_setup = AccountSetupService(executor, gateway)
    market_data = MarketDataService(gateway)

    # Agents (built early for mandate strategy validation)
    agents = build_agents(config)

    # Mandates
    mandate_registry = MandateRegistry(event_store)
    register_mandates(mandate_registry, config)
    validate_mandate_strategies(mandate_registry, agents)
    mandate_validator = MandateValidator(mandate_registry)

    # Risk
    risk_engine = build_risk_engine(config)

    # Session
    session_cfg = config.get("session", {})
    session_manager = SessionManager(
        event_store,
        default_duration_hours=session_cfg.get("default_duration_hours", 8),
    )

    # Alerting (G-003)
    alert_cfg = config.get("alerting", {})
    alert_dispatcher = AlertDispatcher(
        webhook_url=alert_cfg.get("webhook_url", ""),
        severity_filter=alert_cfg.get("severity_filter", "warning"),
        enabled=alert_cfg.get("enabled", False),
    )

    # Restore checkpoint (G-007)
    _restore_checkpoint(event_store, memory)

    # Coordinator
    agent_weights = {a.agent_id: 1.0 for a in agents}
    arbitration = WeightedArbitration(weights=agent_weights)
    portfolio_cfg = config.get("portfolio", {})
    allocator = PortfolioAllocator(
        target_weight=portfolio_cfg.get("max_single_position_weight", 0.02),
        use_kelly=portfolio_cfg.get("use_kelly", False),
        max_kelly_weight=portfolio_cfg.get("max_kelly_weight", 0.05),
    )

    decision_log = config.get("audit", {}).get("decision_log_path", "logs/decision_log.jsonl")
    coordinator = Coordinator(
        arbitration=arbitration,
        allocator=allocator,
        risk_engine=risk_engine,
        memory=memory,
        decision_log_path=decision_log,
        mandate_validator=mandate_validator,
        session_manager=session_manager,
        staging_enabled=config.get("staging", {}).get("enabled", False),
    )

    # Reconciliation
    reconciler = PositionReconciler()
    recon_loop = ReconciliationLoop(
        reconciler=reconciler,
        event_store=event_store,
        pause_callback=lambda: _pause_on_mismatch(live_executor, config),
    )

    # Shutdown with checkpoint
    def _checkpoint() -> None:
        if memory.latest_snapshot:
            event_store.save_portfolio_checkpoint(
                {
                    "nav": memory.latest_snapshot.nav,
                    "positions": len(memory.latest_snapshot.positions),
                }
            )
        event_store.save_memory_checkpoint(
            {
                "peak_nav": memory.peak_nav,
                "rolling_drawdown": memory.rolling_drawdown,
            }
        )
        logger.info("Checkpoint saved on shutdown")

    shutdown = GracefulShutdown(checkpoint_fn=_checkpoint)

    # Register shutdown callbacks (LIFO: cancel first, then checkpoint)
    symbols = list(build_loop_config(config).symbols)

    def _cancel_all() -> None:
        live_executor.cancel_all(symbols)

    shutdown.register_callback(_cancel_all)

    # Build loop
    loop_config = build_loop_config(config)
    loop = TradingLoop(
        coordinator=coordinator,
        live_executor=live_executor,
        fill_tracker=fill_tracker,
        portfolio_sync=portfolio_sync,
        account_setup=account_setup,
        session_manager=session_manager,
        reconciliation_loop=recon_loop,
        shutdown=shutdown,
        gateway=gateway,
        memory=memory,
        agents=agents,
        market_data=market_data,
        config=loop_config,
        alert_dispatcher=alert_dispatcher,
    )

    # Auto-start session in paper/shadow mode (no operator approval needed)
    if mode in (ExecutionMode.PAPER, ExecutionMode.SHADOW):
        session_manager.start_session()
        session_manager.approve_session(operator="system-auto")
        session_manager.activate_session()
        logger.info("Auto-started trading session (paper/shadow mode)")

    logger.info(
        "TradingLoop bootstrapped",
        extra={
            "extra_json": {
                "mode": mode.value,
                "symbols": symbols,
                "agents": [a.agent_id for a in agents],
                "mandates": len(config.get("mandates", [])),
            }
        },
    )
    return loop


def _build_gateway(mode: ExecutionMode) -> MCPGateway:
    """Build the appropriate MCP gateway for the execution mode.

    - PAPER: MockMCPGateway (simulated responses)
    - SHADOW/LIVE: AsterMCPGateway connecting to the MCP server
      configured via AIS_MCP_SERVER_URL env var.
    """
    if mode == ExecutionMode.PAPER:
        logger.info("Using MockMCPGateway (paper mode)")
        return MockMCPGateway()

    server_url = os.environ.get("AIS_MCP_SERVER_URL", "")
    if not server_url:
        raise RuntimeError(
            f"AIS_MCP_SERVER_URL must be set for {mode.value} mode. "
            "Set it to the Aster DEX MCP server endpoint."
        )

    aster_cfg = AsterConfig.from_env()
    gw = AsterMCPGateway(
        server_url=server_url,
        timeout=float(aster_cfg.request_timeout_seconds),
        rate_limit_rps=aster_cfg.rate_limit_calls_per_second,
    )
    logger.info(
        "Using AsterMCPGateway",
        extra={"extra_json": {"url": server_url, "mode": mode.value}},
    )
    return gw


def _restore_checkpoint(event_store: EventStore, memory: SharedMemory) -> None:
    """Restore SharedMemory state from the last checkpoint (G-007)."""
    cp = event_store.load_memory_checkpoint()
    if cp is None:
        logger.info("No memory checkpoint found — starting fresh")
        return
    payload = cp.get("payload", {})
    memory.peak_nav = payload.get("peak_nav", 0.0)
    memory.rolling_drawdown = payload.get("rolling_drawdown", 0.0)
    logger.info(
        "Memory checkpoint restored",
        extra={
            "extra_json": {
                "peak_nav": memory.peak_nav,
                "rolling_drawdown": memory.rolling_drawdown,
                "checkpoint_ts": cp.get("timestamp"),
            }
        },
    )


def _pause_on_mismatch(live_executor: LiveOrderExecutor, config: dict[str, Any]) -> None:
    """Reconciliation mismatch handler: cancel all open orders."""
    symbols = config.get("symbols", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    logger.warning("Position mismatch detected — cancelling all orders")
    live_executor.cancel_all(symbols)
