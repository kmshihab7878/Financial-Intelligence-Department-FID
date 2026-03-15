# Architecture

## System Diagram

```mermaid
graph TD
    D[Data Providers] --> MI[Market Intelligence]
    D --> ST[Strategy Agents]
    MI --> O[Orchestration Layer]
    ST --> O
    O --> PF[Portfolio Allocator]
    PF --> RK[Risk Engine]
    RK -->|approve / veto| O
    O --> EX[Execution]
    EX --> BR[Aster DEX / Simulator]
    BR --> MON[Monitoring]
    O <--> MEM[Shared Memory]
    RK <--> MEM
    PF <--> MEM
    EX <--> MEM
```

## Control Boundary

No executable order may leave orchestration without passing centralized risk validation. Execution components accept only pre-approved order intents carrying a risk approval token.
