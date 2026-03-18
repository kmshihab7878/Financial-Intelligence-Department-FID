"""CLI entry point for the Autonomous Investment Swarm.

Usage:
    python -m aiswarm                      # Paper mode, default config
    python -m aiswarm --mode live           # Live mode
    python -m aiswarm --config ./my-config/ # Custom config directory
    python -m aiswarm --api-only            # Start API server only (no loop)
"""

from __future__ import annotations

import argparse
import os
import sys

from aiswarm.utils.logging import get_logger

logger = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="aiswarm",
        description="Autonomous Investment Swarm — constrained live trading system",
    )
    parser.add_argument(
        "--config",
        default="config/",
        help="Path to configuration directory (default: config/)",
    )
    parser.add_argument(
        "--mode",
        choices=["paper", "shadow", "live"],
        default=None,
        help="Execution mode (overrides config/env)",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="EventStore database path (default: data/ais_events.db)",
    )
    parser.add_argument(
        "--api-only",
        action="store_true",
        help="Start API server only, without trading loop",
    )
    parser.add_argument(
        "--mcp-server-url",
        default=None,
        help="Aster DEX MCP server URL (overrides AIS_MCP_SERVER_URL env var)",
    )
    parser.add_argument(
        "--exchange",
        default=None,
        help="Default exchange to use (e.g. aster, binance, coinbase, bybit, ib)",
    )
    parser.add_argument(
        "--exchanges",
        default=None,
        help="Comma-separated list of exchanges to enable (e.g. aster,binance)",
    )
    parser.add_argument(
        "--tradingview-port",
        type=int,
        default=None,
        help="Port for TradingView webhook listener (enables TV integration)",
    )
    parser.add_argument(
        "--api-host",
        default="0.0.0.0",  # nosec B104 — intentional for container deployment
        help="API server host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=8000,
        help="API server port (default: 8000)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    args = parse_args(argv)

    # Set execution mode env var if specified
    if args.mode:
        os.environ["AIS_EXECUTION_MODE"] = args.mode
    if args.mcp_server_url:
        os.environ["AIS_MCP_SERVER_URL"] = args.mcp_server_url

    if args.api_only:
        return _run_api(args)
    return _run_loop(args)


def _run_api(args: argparse.Namespace) -> int:
    """Start API server only."""
    try:
        import uvicorn

        from aiswarm.api.app import app

        logger.info(
            "Starting API server",
            extra={"extra_json": {"host": args.api_host, "port": args.api_port}},
        )
        uvicorn.run(app, host=args.api_host, port=args.api_port)
        return 0
    except Exception as e:
        logger.error(
            "API server failed",
            extra={"extra_json": {"error": str(e)}},
        )
        return 1


def _run_loop(args: argparse.Namespace) -> int:
    """Bootstrap and run the trading loop."""
    try:
        from prometheus_client import start_http_server

        from aiswarm.bootstrap import bootstrap_from_config

        # Start Prometheus metrics server so the loop's in-process metrics
        # (LOOP_CYCLES, LOOP_CYCLE_DURATION, etc.) are scrapable.
        metrics_port = int(os.environ.get("AIS_LOOP_METRICS_PORT", "9002"))
        start_http_server(metrics_port)
        logger.info(
            "Loop metrics server started",
            extra={"extra_json": {"port": metrics_port}},
        )

        logger.info(
            "Bootstrapping trading loop",
            extra={"extra_json": {"config": args.config, "mode": args.mode}},
        )

        loop = bootstrap_from_config(
            config_dir=args.config,
            db_path=args.db_path,
        )

        # Install signal handlers
        loop.shutdown.install()

        # Run the loop (blocks until shutdown)
        state = loop.run()

        if state.halted:
            logger.error(
                "Loop halted",
                extra={"extra_json": {"reason": state.halt_reason}},
            )
            return 1
        return 0

    except Exception as e:
        logger.error(
            "Fatal error",
            extra={"extra_json": {"error": str(e)}},
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
