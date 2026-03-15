from typing import Any

from fastapi import APIRouter

from aiswarm.monitoring.health import health_status

router = APIRouter()


@router.get("/health")
def get_health() -> dict[str, Any]:
    return health_status()
