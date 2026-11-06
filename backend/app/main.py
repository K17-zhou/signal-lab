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
from app.learning import CASES, CASES_BY_ID, STUDY_FORMS, LearningCase, export_csv, prepare_event
from app.schemas import (
    ExperimentInput, ExperimentResult, LearningEvent, LearningEventRequest, SessionHistory, TutorReply, TutorRequest,
)
from app.store import LearningConflict, Store
from app.study import check_study_step, load_assignments, open_study_store
from app.tutor.client import TutorClient
from app.tutor.service import TutorError, guide

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def create_app(database_path: str | Path | None = None, *, tutor_client: TutorClient | None = None) -> FastAPI:
    database = Path(database_path or os.environ.get(
        "SIGNAL_LAB_DB_PATH", PROJECT_ROOT / ".cache" / "signal-lab.sqlite3"
    ))

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        assignment_path = os.environ.get("SIGNAL_LAB_STUDY_ASSIGNMENTS")
        assignments = load_assignments(PROJECT_ROOT / assignment_path if assignment_path else None)
        application.state.study_assignments = assignments
        application.state.tutor_client = tutor_client if tutor_client is not None else TutorClient.from_environment()
        if assignments:
            with open_study_store(database, assignments) as store:
                application.state.store = store
                yield
        else:
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

    @application.get("/api/evaluation/sessions/{session_id}")
    def study_session(session_id: UUID4, request: Request, response: Response):
        session = str(session_id)
        assignment = request.app.state.study_assignments.get(session)
        if assignment is None:
            raise HTTPException(status_code=404, detail="Study session not found")
        response.headers["Cache-Control"] = "no-store"
        store = request.app.state.store
        events, calls = store.study_history(session)
        return {
            "study": assignment.session_metadata(),
            "cases": STUDY_FORMS[assignment.form],
            "events": events,
            "tutor_calls": calls,
        }

    @application.post("/api/events", response_model=LearningEvent)
    def append_event(payload: LearningEventRequest, request: Request):
        assignment = request.app.state.study_assignments.get(str(payload.session_id))
        available_cases = STUDY_FORMS[assignment.form] if assignment else CASES
        case = CASES_BY_ID.get(payload.case_id)
        if case is None or case not in available_cases:
            raise HTTPException(status_code=404, detail="Learning case not found")
        store = request.app.state.store
        run = store.get_run(str(payload.run_id)) if payload.run_id is not None else None
        if payload.run_id is not None and run is None:
            raise HTTPException(status_code=404, detail="Experiment run not found")
        try:
            if assignment:
                check_study_step(payload, assignment, run, store)
            return store.append_event(prepare_event(payload, case, run), study=assignment is not None)
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
        assignment = request.app.state.study_assignments.get(str(payload.session_id))
        try:
            return await guide(
                payload, request.app.state.store, request.app.state.tutor_client,
                condition=assignment.condition if assignment else None,
            )
        except TutorError as error:
            raise HTTPException(status_code=error.status, detail=str(error)) from error

    @application.get("/api/sessions/{session_id}/export")
    def learning_export(session_id: UUID4, request: Request, format: Literal["json", "csv"] = "json"):
        session = str(session_id)
        store = request.app.state.store
        assignment = request.app.state.study_assignments.get(session)
        if assignment:
            events, calls = store.study_history(session)
            if any(call.status is None for call in calls):
                raise HTTPException(status_code=409, detail="Study guidance is still in progress")
        else:
            events = store.list_events(session)
            calls = []
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
        data = {**history, "runs": runs, "cases": cases}
        if assignment:
            data["study"] = assignment.session_metadata()
            data["tutor_calls"] = [call.model_dump(mode="json") for call in calls]
        return JSONResponse(data, headers=headers)

    frontend = PROJECT_ROOT / "frontend" / "dist"
    if frontend.is_dir():
        application.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return application


app = create_app()
