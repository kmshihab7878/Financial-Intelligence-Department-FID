from fastapi import APIRouter, Depends

from aiswarm.api.auth import require_api_key

router = APIRouter()


@router.get("/reports/latest")
def latest_report(_: str = Depends(require_api_key)) -> dict[str, str]:
    return {"report": "not_generated"}
