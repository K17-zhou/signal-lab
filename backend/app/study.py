"""Frozen, anonymous crossover assignments and study-only workflow rules."""

from collections import defaultdict
from contextlib import closing, contextmanager
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Literal

from pydantic import UUID4, Field

from app.schemas import ExperimentResult, FrozenRecord, LearningEventRequest, TutorMode
from app.store import LearningConflict, Store


class StudyAssignment(FrozenRecord):
    participant_id: str = Field(pattern=r"^[SPT][0-9]{2}$")
    session_id: UUID4
    condition: TutorMode
    form: Literal["X", "Y"]
    order_index: int = Field(ge=1, le=2)
    cohort: Literal["formal", "pilot", "teacher"]
    model_label: str = Field(alias="model_config", min_length=1, max_length=500)

    def session_metadata(self) -> dict:
        return self.model_dump(mode="json", by_alias=True, exclude={"participant_id", "session_id"})


def load_assignments(path: str | Path | None) -> dict[str, StudyAssignment]:
    if not path:
        return {}
    with Path(path).open(encoding="utf-8-sig", newline="") as source:
        rows = [StudyAssignment.model_validate(row) for row in csv.DictReader(source)]
    by_session = {str(row.session_id): row for row in rows}
    if len(by_session) != len(rows) or not rows:
        raise ValueError("Study assignment file must contain unique session IDs")
    if len({row.model_label for row in rows}) != 1:
        raise ValueError("Study sessions must share one model configuration")
    by_participant: dict[str, list[StudyAssignment]] = defaultdict(list)
    for row in rows:
        by_participant[row.participant_id].append(row)
    for pair in by_participant.values():
        if (
            len(pair) != 2 or {row.condition for row in pair} != {"B", "C"}
            or {row.form for row in pair} != {"X", "Y"}
            or {row.order_index for row in pair} != {1, 2}
            or len({row.cohort for row in pair}) != 1
        ):
            raise ValueError("Each participant needs two different conditions and forms in a fixed order")
    return by_session


@contextmanager
def open_study_store(database: Path, assignments: dict[str, StudyAssignment]):
    if not assignments:
        yield Store(database)
        return
    database = database.resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    # A separate SQLite file lets the process hold the study lock without blocking event writes.
    lock_path = database.with_name(database.name + ".study-lock.sqlite3")
    frozen = {session: assignment.model_dump(mode="json", by_alias=True) for session, assignment in assignments.items()}
    fingerprint = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode("utf-8")).hexdigest()
    with closing(sqlite3.connect(lock_path, timeout=0)) as lock:
        try:
            lock.execute("BEGIN EXCLUSIVE")
        except sqlite3.OperationalError as error:
            raise RuntimeError("A study service is already active for this database") from error
        store = Store(database, study_fingerprint=fingerprint)
        store.recover_study_tutor_calls()
        yield store


def check_study_step(
    request: LearningEventRequest, assignment: StudyAssignment, run: ExperimentResult | None, store: Store,
) -> None:
    if request.stage not in ("observe", "transfer"):
        return
    call = store.get_study_tutor_call(str(request.session_id), request.case_id)
    if call is None or call.status is None:
        raise LearningConflict("Complete the guidance request before this step")
    if request.stage == "observe":
        proposal = call.reply.next_experiment if call.reply else None
        if assignment.condition != "C" or proposal is None or run is None or run.params != proposal.params:
            raise LearningConflict("The comparison must match this session's saved suggestion")
