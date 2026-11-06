"""Append-only experiment storage; each operation owns its SQLite connection."""

from contextlib import closing
from pathlib import Path
import sqlite3

from pydantic import TypeAdapter

from app.schemas import ExperimentResult, LearningEvent, StudyTutorCall


_RUN_ADAPTER = TypeAdapter(ExperimentResult)


class LearningConflict(ValueError):
    """A saved event or learning stage conflicts with the submission."""


class Store:
    def __init__(self, database_path: str | Path, *, study_fingerprint: str | None = None):
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
                """
                CREATE UNIQUE INDEX IF NOT EXISTS learning_run_owner
                ON learning_events(run_id) WHERE stage IN ('run', 'observe')
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS study_tutor_calls (
                    session_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (session_id, case_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS study_binding (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    assignment_fingerprint TEXT NOT NULL
                )
                """
            )
            binding = connection.execute("SELECT assignment_fingerprint FROM study_binding WHERE id = 1").fetchone()
            if binding and binding[0] != study_fingerprint:
                raise RuntimeError("This database requires its original study assignments")
            if not binding and study_fingerprint:
                connection.execute("INSERT INTO study_binding VALUES (1, ?)", (study_fingerprint,))
            connection.commit()

    def put_run(self, run: ExperimentResult) -> None:
        with closing(sqlite3.connect(self.path, timeout=5)) as connection:
            try:
                connection.execute(
                    "INSERT INTO runs (run_id, payload) VALUES (?, ?)",
                    (run.run_id, run.model_dump_json()),
                )
                connection.commit()
            except sqlite3.IntegrityError as error:
                raise ValueError("An experiment with this run_id already exists") from error

    def get_run(self, run_id: str) -> ExperimentResult | None:
        with closing(sqlite3.connect(self.path, timeout=5)) as connection:
            row = connection.execute(
                "SELECT payload FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return _RUN_ADAPTER.validate_json(row[0]) if row else None

    def append_event(self, event: LearningEvent, *, study: bool = False) -> LearningEvent:
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
            if study and event.stage == "observe":
                prior_comparison = connection.execute(
                    "SELECT 1 FROM learning_events WHERE session_id = ? AND case_id = ? AND stage = 'observe'",
                    (session_id, event.case_id),
                ).fetchone()
                if prior_comparison or "transfer" in stages:
                    raise LearningConflict("This comparison step is already closed")
            if event.stage in ("run", "observe"):
                prerequisite = "predict" if event.stage == "run" else "run"
                if prerequisite not in stages:
                    raise LearningConflict("Save the previous learning step before recording this run")
                owner = connection.execute(
                    "SELECT 1 FROM learning_events WHERE stage IN ('run', 'observe') AND run_id = ?", (run_id,)
                ).fetchone()
                if owner:
                    raise LearningConflict("This run already belongs to a learning case")
            elif run_id is not None and stages.get("run") != run_id:
                observation = None
                if event.stage != "transfer":
                    observation = connection.execute(
                        """
                        SELECT 1 FROM learning_events
                        WHERE session_id = ? AND case_id = ? AND stage = 'observe' AND run_id = ?
                        """,
                        (session_id, event.case_id, run_id),
                    ).fetchone()
                if not observation:
                    raise LearningConflict("This run is not recorded for this learning step")

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
            return self._read_events(connection, session_id)

    @staticmethod
    def _read_events(connection: sqlite3.Connection, session_id: str) -> list[LearningEvent]:
        rows = connection.execute(
            "SELECT payload FROM learning_events WHERE session_id = ? ORDER BY rowid", (session_id,)
        ).fetchall()
        return [LearningEvent.model_validate_json(row[0]) for row in rows]

    def reserve_study_tutor_call(self, session_id: str, call: StudyTutorCall) -> bool:
        with closing(sqlite3.connect(self.path, timeout=5)) as connection, connection:
            result = connection.execute(
                "INSERT INTO study_tutor_calls VALUES (?, ?, ?) ON CONFLICT(session_id, case_id) DO NOTHING",
                (session_id, call.case_id, call.model_dump_json()),
            )
            return result.rowcount == 1

    def save_study_tutor_call(self, session_id: str, call: StudyTutorCall) -> bool:
        with closing(sqlite3.connect(self.path, timeout=5)) as connection, connection:
            result = connection.execute(
                """
                UPDATE study_tutor_calls SET payload = ?
                WHERE session_id = ? AND case_id = ? AND json_extract(payload, '$.status') IS NULL
                """,
                (call.model_dump_json(), session_id, call.case_id),
            )
            return result.rowcount == 1

    def get_study_tutor_call(self, session_id: str, case_id: str) -> StudyTutorCall | None:
        with closing(sqlite3.connect(self.path, timeout=5)) as connection:
            row = connection.execute(
                "SELECT payload FROM study_tutor_calls WHERE session_id = ? AND case_id = ?",
                (session_id, case_id),
            ).fetchone()
        return StudyTutorCall.model_validate_json(row[0]) if row else None

    def study_history(self, session_id: str) -> tuple[list[LearningEvent], list[StudyTutorCall]]:
        with closing(sqlite3.connect(self.path, timeout=5)) as connection:
            connection.execute("BEGIN")
            events = self._read_events(connection, session_id)
            rows = connection.execute(
                "SELECT payload FROM study_tutor_calls WHERE session_id = ? ORDER BY rowid",
                (session_id,),
            ).fetchall()
        return events, [StudyTutorCall.model_validate_json(row[0]) for row in rows]

    def recover_study_tutor_calls(self) -> None:
        with closing(sqlite3.connect(self.path, timeout=5)) as connection, connection:
            connection.execute(
                """
                UPDATE study_tutor_calls
                SET payload = json_set(payload, '$.status', 500, '$.error_code', 'tutor_interrupted')
                WHERE json_extract(payload, '$.status') IS NULL
                """
            )
