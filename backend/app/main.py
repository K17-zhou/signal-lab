"""Local application API with an optional built frontend on the same origin."""

from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import UUID4

from app.experiments.runner import run_experiment
from app.experiments.sampling import ENGINE_VERSION
from app.learning import CASES, CASES_BY_ID, LearningCase, export_csv, prepare_event
from app.schemas import (
    ExperimentInput, ExperimentResult, LearningEvent, LearningEventRequest, SessionHistory, TutorReply, TutorRequest,
)
from app.store import LearningConflict, Store
from app.tutor.client import TutorClient
from app.tutor.service import TutorError, guide

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def create_app(database_path: str | Path | None = None, *, tutor_client: TutorClient | None = None) -> FastAPI:
    database = Path(database_path or os.environ.get(
        "SIGNAL_LAB_DB_PATH", PROJECT_ROOT / ".cache" / "signal-lab.sqlite3"
    ))

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.store = Store(database)
        application.state.tutor_client = tutor_client if tutor_client is not None else TutorClient.from_environment()
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

    @application.post("/api/experiments/run", response_model=ExperimentResult)
    def compute(payload: ExperimentInput, request: Request):
        run = run_experiment(payload)
        request.app.state.store.put_run(run)
        return run

    @application.get("/api/experiments/{run_id}", response_model=ExperimentResult)
    def retrieve(run_id: str, request: Request):
        run = request.app.state.store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Experiment run not found")
        return run

    @application.get("/api/learning/cases", response_model=list[LearningCase])
    def learning_cases():
        return CASES

    @application.post("/api/events", response_model=LearningEvent)
    def append_event(payload: LearningEventRequest, request: Request):
        case = CASES_BY_ID.get(payload.case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Learning case not found")
        store = request.app.state.store
        run = store.get_run(str(payload.run_id)) if payload.run_id is not None else None
        if payload.run_id is not None and run is None:
            raise HTTPException(status_code=404, detail="Experiment run not found")
        try:
            return store.append_event(prepare_event(payload, case, run))
        except LearningConflict as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.get("/api/sessions/{session_id}/events", response_model=SessionHistory)
    def learning_history(session_id: UUID4, request: Request, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return SessionHistory(session_id=session_id, events=request.app.state.store.list_events(str(session_id)))

    @application.post("/api/tutor/guide", response_model=TutorReply)
    async def tutor_guide(payload: TutorRequest, request: Request):
        try:
            return await guide(payload, request.app.state.store, request.app.state.tutor_client)
        except TutorError as error:
            raise HTTPException(status_code=error.status, detail=str(error)) from error

    @application.get("/api/sessions/{session_id}/export")
    def learning_export(session_id: UUID4, request: Request, format: Literal["json", "csv"] = "json"):
        store = request.app.state.store
        events = store.list_events(str(session_id))
        runs = {}
        for run_id in {str(event.run_id) for event in events if event.run_id is not None}:
            run = store.get_run(run_id)
            if run is not None:
                runs[run_id] = run.model_dump(mode="json", exclude={"series"})
        headers = {
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="signal-lab-{session_id}.{format}"',
        }
        if format == "csv":
            return Response(export_csv(events, runs), media_type="text/csv", headers=headers)
        history = SessionHistory(session_id=session_id, events=events).model_dump(mode="json")
        cases = {event.case_id: CASES_BY_ID[event.case_id].model_dump(mode="json") for event in events}
        return JSONResponse({**history, "runs": runs, "cases": cases}, headers=headers)

    frontend = PROJECT_ROOT / "frontend" / "dist"
    if frontend.is_dir():
        application.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return application


app = create_app()
