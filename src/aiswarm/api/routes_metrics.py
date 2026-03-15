from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

router = APIRouter()


@router.get("/metrics-summary")
def metrics_summary() -> dict[str, str]:
    return {"metrics": "prometheus endpoint available at /metrics"}


@router.get("/metrics")
def prometheus_metrics() -> PlainTextResponse:
    return PlainTextResponse(
        content=generate_latest().decode("utf-8"),
        media_type=CONTENT_TYPE_LATEST,
    )
