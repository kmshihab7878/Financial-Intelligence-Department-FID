# Operating Model

> **Note**: This document describes the target operating model. Not all steps are fully implemented in the current codebase. The system is an experimental scaffold under active development.

## 12-step operating loop
1. Ingest market, macro, fundamental, technical, and alternative data.
2. Normalize and enrich the data into canonical entities.
3. Classify market regime, liquidity state, and volatility context.
4. Generate candidate opportunities across strategies and assets.
5. Forecast distributions, scenario ranges, and confidence.
6. Cross-validate candidate theses across specialist agents.
7. Rank opportunities by expected return, confidence, liquidity, and regime fit.
8. Construct or rebalance the portfolio under portfolio-level constraints.
9. Run pre-trade risk validation and veto checks.
10. Execute approved orders using cost-aware routing and scheduling.
11. Monitor fills, exposure, PnL, health, and incidents in real time.
12. Review attribution, detect drift, run challenger tests, and evolve under governance.

## Governance model
Humans define mandates, allowed assets, risk budgets, compliance constraints, and override conditions. AIS operates within those boundaries and escalates incidents or policy breaches.
