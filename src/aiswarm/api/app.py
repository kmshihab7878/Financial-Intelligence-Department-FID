from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from aiswarm import __version__
from aiswarm.api.routes_control import router as control_router
from aiswarm.api.routes_health import router as health_router
from aiswarm.api.routes_mandates import router as mandates_router
from aiswarm.api.routes_metrics import router as metrics_router
from aiswarm.api.routes_reports import router as reports_router
from aiswarm.api.routes_session import router as session_router

app = FastAPI(title="Autonomous Investment Swarm", version=__version__)

# Static files (dashboard)
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/")
def dashboard() -> FileResponse:
    return FileResponse(str(_static_dir / "dashboard.html"))


# Public routes
app.include_router(health_router, tags=["health"])
app.include_router(metrics_router, tags=["metrics"])

# Authenticated routes
app.include_router(control_router, tags=["control"])
app.include_router(reports_router, tags=["reports"])
app.include_router(mandates_router, tags=["mandates"])
app.include_router(session_router, tags=["session"])
