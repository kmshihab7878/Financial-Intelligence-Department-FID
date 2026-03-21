# Architecture Overview

AIS is built around a simple principle: **no order executes without cryptographic risk approval**. The architecture enforces this through a layered pipeline where each component has a single responsibility.

## System Architecture

```mermaid
graph TD
    subgraph "Data Layer"
        DP[Exchange Providers]
        ES[Event Store]
    end

    subgraph "Intelligence Layer"
        MI[Market Intelligence]
        SA[Strategy Agents]
    end

    subgraph "Orchestration Layer"
        WA[Weighted Arbitration]
        CO[Coordinator]
        SM[Shared Memory]
    end

    subgraph "Risk Layer"
        PA[Portfolio Allocator]
        RE[Risk Engine]
        KS[Kill Switch]
        DG[Drawdown Guard]
        LG[Leverage Guard]
        LQ[Liquidity Guard]
    end

    subgraph "Execution Layer"
        OMS[Order Management]
        FT[Fill Tracker]
        EXP[Exchange Providers]
    end

    subgraph "Observability"
        PM[Prometheus Metrics]
        RC[Reconciliation]
        AL[Alert Manager]
    end

    DP --> MI
    DP --> SA
    MI --> WA
    SA --> WA
    WA --> CO
    CO --> PA
    PA --> RE
    RE --> DG & LG & LQ
    RE -->|HMAC Token| OMS
    KS -.->|Emergency| OMS
    OMS --> EXP
    EXP --> FT
    FT --> PM
    CO <--> SM
    RE <--> SM
    CO --> ES
    EXP --> RC
    RC --> AL

    style RE fill:#e8eaf6,stroke:#5e35b1,stroke-width:2px
    style KS fill:#ffebee,stroke:#c62828,stroke-width:2px
```

## Trading Cycle

Every 60 seconds, the coordinator executes one complete cycle:

```mermaid
sequenceDiagram
    participant L as Trading Loop
    participant C as Coordinator
    participant A as Strategy Agents
    participant W as Arbitration
    participant P as Portfolio Allocator
    participant R as Risk Engine
    participant O as OMS
    participant E as Exchange

    L->>C: tick()
    C->>A: analyze(market_data)
    A-->>C: Signal[]
    C->>W: select_signal(signals)
    W-->>C: best_signal
    C->>P: order_from_signal(signal, snapshot)
    P-->>C: Order (PENDING)
    C->>R: validate(order)
    alt Approved
        R-->>C: Order (APPROVED + HMAC token)
        C->>O: submit(order)
        O->>O: verify HMAC token
        O->>E: execute(order)
        E-->>O: ExecutionResult
    else Rejected
        R-->>C: RiskEvent (reason)
        C->>C: log rejection
    end
    C->>C: update shared memory
    C->>C: persist decision log
```

## Component Responsibilities

### Data Layer
- **Exchange Providers** — Fetch market data (klines, ticker, order book, funding rates) from exchanges via MCP
- **Event Store** — Append-only SQLite store for decisions, orders, risk events, and fills

### Intelligence Layer
- **Strategy Agents** — Generate `Signal` objects from market data. Each agent implements `analyze()`, `propose()`, and `validate()`
- **Market Intelligence** — Specialized agents for market structure analysis (funding rates, regime detection)

### Orchestration Layer
- **Coordinator** — Runs the trading cycle, routes data between components
- **Weighted Arbitration** — Selects the best signal from competing agents using `weight * confidence * return * liquidity`
- **Shared Memory** — Maintains live portfolio state (NAV, drawdown, leverage, positions)

### Risk Layer
- **Portfolio Allocator** — Converts signals to orders with position sizing (target weight * confidence)
- **Risk Engine** — Validates orders against all guards, signs approved orders with HMAC tokens
- **Kill Switch** — Emergency stop triggered by daily loss or manual activation
- **Guards** — Drawdown, leverage, liquidity, and exposure checks

### Execution Layer
- **OMS** — Verifies HMAC tokens, transitions order status, routes to exchange
- **Fill Tracker** — Records execution results and updates order status
- **Exchange Providers** — Submit orders to exchanges (paper/shadow/live)

### Observability
- **Prometheus Metrics** — P&L, exposure, drawdown, agent latency, order rates
- **Reconciliation** — Compares internal state against exchange positions
- **Alertmanager** — Dispatches alerts for risk events and anomalies

## Design Principles

1. **Fail closed** — Missing secrets, invalid tokens, or unreachable services cause the system to stop, not proceed with defaults
2. **HMAC-signed risk approval** — Cryptographic proof that the risk engine approved each order
3. **Append-only audit** — Every decision, order, and risk event is persisted and immutable
4. **Mode parity** — Paper, shadow, and live modes share the same code path
5. **Config-driven routing** — Exchange and symbol routing is declarative, not hardcoded

## Directory Structure

```
src/aiswarm/
├── agents/             # Strategy agents
│   ├── base.py             # Agent ABC
│   ├── market_intelligence/ # Market structure agents
│   └── strategy/           # Signal generation agents
├── api/                # FastAPI control plane
├── backtest/           # Backtesting engine
├── bootstrap.py        # Config → component graph
├── data/               # Event store, data providers
├── exchange/           # Multi-exchange abstraction
│   ├── provider.py         # ExchangeProvider ABC
│   ├── registry.py         # ExchangeRegistry
│   ├── symbols.py          # SymbolRouter
│   └── providers/          # Exchange implementations
├── execution/          # Order management, fill tracking
├── integrations/       # TradingView, portfolio trackers, tax
├── loop/               # Trading loop (60s cycle)
├── mandates/           # Governance system
├── monitoring/         # Metrics, alerts, reconciliation
├── orchestration/      # Coordinator, arbitration, memory
├── portfolio/          # Allocator, exposure manager
├── quant/              # Kelly, risk metrics, drift detection
├── resilience/         # Circuit breaker, rate limiter
├── risk/               # Risk engine, kill switch, guards
├── session/            # Session lifecycle
├── types/              # Pydantic domain models
└── utils/              # Logging, secrets, time
```
