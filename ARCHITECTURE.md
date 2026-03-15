# Architecture

## System diagram
```mermaid
graph TD
    D[Data Providers] --> MI[Market Intelligence Cluster]
    D --> ST[Strategy Cluster]
    D --> FC[Forecasting Cluster]
    MI --> O[Orchestration Layer]
    ST --> O
    FC --> O
    O --> PF[Portfolio Cluster]
    PF --> RK[Risk Cluster]
    RK -->|approve/veto| O
    O --> EX[Execution Cluster]
    EX --> BR[Broker / Exchange / Simulator]
    BR --> MON[Monitoring & Attribution]
    MON --> OV[Oversight & Evolution Cluster]
    OV --> O
    O <--> MEM[Shared Memory / Portfolio State]
    RK <--> MEM
    PF <--> MEM
    EX <--> MEM
```

## Control boundary
No executable order may leave orchestration without passing centralized risk validation. Execution components accept only pre-approved order intents carrying a risk approval token.
