"""Local application API with an optional built frontend on the same origin."""

from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.experiments.runner import run_experiment
from app.experiments.sampling import ENGINE_VERSION
from app.schemas import ExperimentRequest, ExperimentRun
from app.store import Store

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def create_app(database_path: str | Path | None = None) -> FastAPI:
    database = Path(database_path or os.environ.get(
        "SIGNAL_LAB_DB_PATH", PROJECT_ROOT / ".cache" / "signal-lab.sqlite3"
    ))

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.store = Store(database)
        yield

    application = FastAPI(title="信号实验工坊", version="0.2.0", lifespan=lifespan)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, error: RequestValidationError):
        # Do not echo NaN/Infinity or arbitrary input into JSON error responses.
        return JSONResponse(status_code=422, content={"detail": [
            {"loc": list(item["loc"]), "msg": item["msg"], "type": item["type"]}
            for item in error.errors()
        ]})

    @application.get("/api/health")
    def health():
        return {"status": "ok", "engine_version": ENGINE_VERSION}

    @application.post("/api/experiments/run", response_model=ExperimentRun)
    def compute(payload: ExperimentRequest, request: Request):
        run = run_experiment(payload)
        request.app.state.store.put_run(run)
        return run

    @application.get("/api/experiments/{run_id}", response_model=ExperimentRun)
    def retrieve(run_id: str, request: Request):
        run = request.app.state.store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Experiment run not found")
        return run

    frontend = PROJECT_ROOT / "frontend" / "dist"
    if frontend.is_dir():
        application.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return application


app = create_app()
