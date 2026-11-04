"""Append-only experiment storage; each operation owns its SQLite connection."""

from contextlib import closing
from pathlib import Path
import sqlite3

from app.schemas import ExperimentRun, LearningEvent


class LearningConflict(ValueError):
    """A saved event or learning stage conflicts with the submission."""


class Store:
    def __init__(self, database_path: str | Path):
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS learning_events (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    run_id TEXT REFERENCES runs(run_id),
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS learning_session ON learning_events(session_id, case_id, stage)"
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS learning_run ON learning_events(run_id) WHERE stage = 'run'"
            )
            connection.commit()

    def put_run(self, run: ExperimentRun) -> None:
        with closing(sqlite3.connect(self.path, timeout=5)) as connection:
            try:
                connection.execute(
                    "INSERT INTO runs (run_id, payload) VALUES (?, ?)",
                    (run.run_id, run.model_dump_json()),
                )
                connection.commit()
            except sqlite3.IntegrityError as error:
                raise ValueError("An experiment with this run_id already exists") from error

    def get_run(self, run_id: str) -> ExperimentRun | None:
        with closing(sqlite3.connect(self.path, timeout=5)) as connection:
            row = connection.execute(
                "SELECT payload FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return ExperimentRun.model_validate_json(row[0]) if row else None

    def append_event(self, event: LearningEvent) -> LearningEvent:
        event_id = str(event.event_id)
        session_id = str(event.session_id)
        run_id = str(event.run_id) if event.run_id is not None else None
        with closing(sqlite3.connect(self.path, timeout=5)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            saved = connection.execute(
                "SELECT payload FROM learning_events WHERE event_id = ?", (event_id,)
            ).fetchone()
            if saved:
                original = LearningEvent.model_validate_json(saved[0])
                server_fields = {"timestamp", "outcome"}
                if original.model_dump(exclude=server_fields) != event.model_dump(exclude=server_fields):
                    raise LearningConflict("This event ID already has different content")
                return original

            stages = dict(connection.execute(
                """
                SELECT stage, run_id FROM learning_events
                WHERE session_id = ? AND case_id = ? AND stage IN ('predict', 'run', 'transfer')
                """,
                (session_id, event.case_id),
            ))
            if event.stage in stages:
                raise LearningConflict("This stage already has a saved record")
            if event.stage == "run":
                if "predict" not in stages:
                    raise LearningConflict("Save the prediction before recording a run")
                owner = connection.execute(
                    "SELECT 1 FROM learning_events WHERE stage = 'run' AND run_id = ?", (run_id,)
                ).fetchone()
                if owner:
                    raise LearningConflict("This run already belongs to a learning case")
            elif run_id is not None and stages.get("run") != run_id:
                raise LearningConflict("This run is not recorded for the session and case")

            connection.execute(
                """
                INSERT INTO learning_events (event_id, session_id, case_id, stage, run_id, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_id, session_id, event.case_id, event.stage, run_id, event.model_dump_json()),
            )
        return event

    def list_events(self, session_id: str) -> list[LearningEvent]:
        with closing(sqlite3.connect(self.path, timeout=5)) as connection:
            rows = connection.execute(
                "SELECT payload FROM learning_events WHERE session_id = ? ORDER BY rowid", (session_id,)
            ).fetchall()
        return [LearningEvent.model_validate_json(row[0]) for row in rows]
