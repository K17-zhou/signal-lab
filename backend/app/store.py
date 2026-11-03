"""Append-only experiment storage; each operation owns its SQLite connection."""

from contextlib import closing
from pathlib import Path
import sqlite3

from app.schemas import ExperimentRun


class Store:
    def __init__(self, database_path: str | Path):
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
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
