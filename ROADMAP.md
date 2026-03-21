# Roadmap

This roadmap outlines the planned development direction for AIS. Milestones are subject to change based on community feedback and research outcomes.

## v1.3 — Strategy Framework Expansion

- [ ] Champion/challenger framework for automated strategy evaluation
- [ ] Shadow deployment of strategy variants alongside incumbents
- [ ] Statistical comparison of risk-adjusted returns over evaluation windows
- [ ] Mean-reversion strategy agent
- [ ] Volatility breakout strategy agent
- [ ] Strategy backtesting integration with live agent interface

## v1.4 — Advanced Risk & Portfolio

- [ ] Multi-asset correlation-aware portfolio construction
- [ ] Dynamic position sizing using real-time volatility estimates
- [ ] Regime-adaptive risk limits (tighter in stressed regimes)
- [ ] Cross-exchange margin aggregation
- [ ] Slippage model with historical calibration
- [ ] Monte Carlo risk simulation for portfolio stress testing

## v1.5 — Production Hardening

- [ ] PostgreSQL event store (migrate from SQLite)
- [ ] Redis Streams for inter-service communication
- [ ] Kubernetes deployment manifests with Helm charts
- [ ] Horizontal scaling: multiple loop instances with leader election
- [ ] OpenTelemetry tracing across the full order lifecycle
- [ ] Alertmanager runbooks for common incidents

## v2.0 — Autonomous Evolution

- [ ] Agent self-evaluation and parameter tuning
- [ ] Automated promotion/rollback based on significance testing
- [ ] Multi-account mandate partitioning
- [ ] Regulatory compliance reporting module
- [ ] Strategy marketplace for community-contributed agents
- [ ] Web dashboard for session management and monitoring

## Research Track

These are longer-term explorations without committed timelines:

- Reinforcement learning agents for adaptive strategy selection
- Cross-chain arbitrage with MEV-aware execution
- Natural language thesis generation for audit narratives
- On-chain settlement verification
- Alternative data integration (sentiment, flow, on-chain)

---

Have ideas? Open a [feature request](https://github.com/kmshihab7878/Autonomous-Investment-Swarm/issues/new?template=feature_request.yml) or start a [discussion](https://github.com/kmshihab7878/Autonomous-Investment-Swarm/discussions).
