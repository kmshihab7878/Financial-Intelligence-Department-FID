from __future__ import annotations
from enum import Enum


class WorkflowStage(str, Enum):
    INGEST = "ingest"
    ANALYZE = "analyze"
    PROPOSE = "propose"
    RISK_VALIDATE = "risk_validate"
    EXECUTE = "execute"
    MONITOR = "monitor"
    EVOLVE = "evolve"
