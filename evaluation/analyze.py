"""Summarize the recorded B/C evaluation without altering the source records."""

import argparse
from collections import Counter, defaultdict
from collections.abc import Sequence
import csv
import json
from pathlib import Path
from statistics import median
import sys


_EVALUATION = Path(__file__).resolve().parent
_CONDITIONS = ("B", "C")
_FORMS = ("X", "Y")
_TOPICS = ("safe", "alias", "boundary")
_COHORTS = {
    "formal": {f"S{number:02d}" for number in range(1, 13)},
    "pilot": {"P01", "P02", "P03"},
    "teacher": {"T01"},
}
_SOURCES = ("human", "synthetic")
_ATTENDANCE_STATUSES = ("started", "stopped")
_STUDY_FIELDS = ("condition", "form", "order_index", "cohort", "model_config")
_ASSIGNMENT_FIELDS = ("participant_id", "session_id", *_STUDY_FIELDS)
_ATTENDANCE_FIELDS = ("participant_id", "source", "status")
_AUDIT_FIELDS = ("session_id", "case_id", "has_numeric_error")
_STAGE_OUTCOMES = {
    "predict": ("recorded",),
    "run": ("completed",),
    "observe": ("completed",),
    "reflect": ("recorded",),
    "transfer": ("correct", "incorrect"),
    "export": ("completed",),
    "error": ("failed",),
}


def _text(row, field: str) -> str:
    value = row.get(field) if isinstance(row, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Expected nonempty {field}")
    return value


def _form_cases(forms: dict | None) -> dict[str, dict[str, dict]]:
    if not isinstance(forms, dict) or set(forms) != set(_FORMS):
        raise ValueError("Expected frozen forms X and Y")
    by_form = {}
    for form, cases in forms.items():
        expected = {f"study-{form.lower()}-{topic}" for topic in _TOPICS}
        if not isinstance(cases, list) or len(cases) != len(expected):
            raise ValueError(f"Form {form} must contain its three frozen cases")
        by_id = {_text(case, "case_id"): case for case in cases}
        if by_id.keys() != expected:
            raise ValueError(f"Form {form} has unexpected case IDs")
        by_form[form] = by_id
    return by_form


def _registered_answer(answer, question) -> bool:
    if not isinstance(answer, dict) or not isinstance(question, dict):
        return False
    kind = question.get("kind")
    if answer.get("kind") != kind:
        return False
    if kind == "choice":
        option_id = answer.get("option_id")
        options = question.get("options")
        return (
            answer.keys() == {"kind", "option_id"}
            and isinstance(option_id, str) and 1 <= len(option_id) <= 64
            and isinstance(options, list)
            and any(isinstance(option, dict) and option.get("option_id") == option_id for option in options)
        )
    value = answer.get("value")
    unit = answer.get("unit")
    return (
        kind == "numeric" and answer.keys() == {"kind", "value", "unit"}
        and type(value) in (int, float) and -sys.float_info.max <= value <= sys.float_info.max
        and unit in ("Hz", "ratio") and unit == question.get("unit")
    )


def _assignment_index(assignments: Sequence[dict]) -> tuple[dict, dict]:
    by_session = {}
    by_participant = defaultdict(list)
    for row in assignments:
        participant = _text(row, "participant_id")
        session = _text(row, "session_id")
        cohort = _text(row, "cohort")
        condition = _text(row, "condition")
        form = _text(row, "form")
        model = _text(row, "model_config")
        period = row.get("order_index")
        if participant not in _COHORTS.get(cohort, ()):
            raise ValueError(f"Assignment cohort does not match participant {participant}")
        if session in by_session or session != session.strip():
            raise ValueError(f"Invalid or duplicate assignment session_id {session}")
        if condition not in _CONDITIONS or form not in _FORMS:
            raise ValueError(f"Invalid condition or form for session {session}")
        if type(period) not in (str, int) or str(period) not in ("1", "2"):
            raise ValueError(f"Invalid assignment period for session {session}")
        assignment = {
            "participant_id": participant, "condition": condition, "form": form,
            "order_index": int(period), "cohort": cohort, "model_config": model,
        }
        by_session[session] = assignment
        by_participant[participant].append(assignment)

    formal_models = set()
    for participant, periods in by_participant.items():
        if len(periods) != 2 or any(
            {period[field] for period in periods} != expected
            for field, expected in (("condition", {"B", "C"}), ("form", {"X", "Y"}), ("order_index", {1, 2}))
        ):
            raise ValueError(f"Expected both assigned periods for participant {participant}")
        models = {period["model_config"] for period in periods}
        if len(models) != 1:
            raise ValueError(f"Model configuration differs between periods for participant {participant}")
        if periods[0]["cohort"] == "formal":
            formal_models.update(models)
    if len(formal_models) > 1:
        raise ValueError("The formal assignments use different model configurations")
    return by_session, {participant: periods[0]["cohort"] for participant, periods in by_participant.items()}


def _attendance_index(attendance: Sequence[dict], cohorts: dict[str, str]) -> tuple[dict, dict]:
    counts = {
        cohort: {source: dict.fromkeys(_ATTENDANCE_STATUSES, 0) for source in _SOURCES}
        for cohort in _COHORTS
    }
    sources = {}
    for row in attendance:
        participant = _text(row, "participant_id")
        source = _text(row, "source")
        status = _text(row, "status")
        if participant not in cohorts or participant in sources:
            raise ValueError(f"Unknown or duplicate attendance participant {participant}")
        if source not in _SOURCES or status not in _ATTENDANCE_STATUSES:
            raise ValueError(f"Invalid attendance source or status for participant {participant}")
        sources[participant] = source
        counts[cohorts[participant]][source][status] += 1
    return sources, counts


def _elapsed_ms(row: dict, *, allow_missing: bool = False) -> int | None:
    value = row.get("elapsed_ms")
    if value is None and allow_missing and "elapsed_ms" in row:
        return None
    if type(value) is not int or not 0 <= value <= 2**63 - 1:
        raise ValueError("Expected nonnegative integer elapsed_ms")
    return value


def _distribution(samples: list[int]) -> dict:
    return {
        "n": len(samples),
        "min": min(samples, default=None),
        "median": median(samples) if samples else None,
        "max": max(samples, default=None),
    }


def _condition_metrics(sessions: set[str], tasks: int, exports: set[str], events, calls, audits) -> dict:
    stage_times = {stage: [] for stage in _STAGE_OUTCOMES}
    transfers = Counter()
    for event in events:
        if event["session_id"] not in sessions:
            continue
        stage = event["stage"]
        stage_times[stage].append(event["elapsed_ms"])
        if stage == "transfer":
            transfers[event["outcome"]] += 1

    statuses = Counter()
    tutor_times = []
    reviewed = []
    for key, call in calls.items():
        if key[0] not in sessions:
            continue
        statuses[call["status"]] += 1
        if call["elapsed_ms"] is not None:
            tutor_times.append(call["elapsed_ms"])
        if key in audits:
            reviewed.append(audits[key])

    completed = sum(transfers.values())
    attempts = sum(statuses.values())
    return {
        "assigned_tasks": tasks,
        "completed_tasks": completed,
        "completion_rate": completed / tasks if tasks else None,
        "transfer_correct": transfers["correct"],
        "transfer_incorrect": transfers["incorrect"],
        "incomplete_tasks": tasks - completed,
        "exported_sessions": len(sessions & exports),
        "missing_exports": len(sessions - exports),
        "stage_errors": len(stage_times["error"]),
        "elapsed_ms_by_stage": {stage: _distribution(samples) for stage, samples in stage_times.items()},
        "tutor": {
            "calls": attempts,
            "successes": statuses[200],
            "failures": attempts - statuses[200] - statuses[None],
            "interrupted": statuses[None],
            "elapsed_ms": _distribution(tutor_times),
            "audit": {
                "audited_replies": len(reviewed),
                "missing_audits": statuses[200] - len(reviewed),
                "numeric_errors": sum(reviewed),
            },
        },
    }


def analyze(
    events: list[dict],
    *,
    assignments: Sequence[dict] = (),
    forms: dict | None = None,
    attendance: Sequence[dict] = (),
    tutor_calls: Sequence[dict] = (),
    feedback_audit: Sequence[dict] = (),
    session_studies: dict[str, dict] | None = None,
) -> dict:
    """Analyze formal human starters, including periods without an export.

    Events use the saved order within each session. ``tutor_calls`` are flattened
    with their session_id. ``session_studies`` provides the study metadata of
    each loaded export, including empty exports.
    When omitted, export coverage is inferred from the supplied event and call rows.
    Tutor failures have recorded non-200 statuses. Calls without a status are
    reported separately, and latency statistics use recorded durations only.
    """
    form_cases = _form_cases(forms) if assignments or forms is not None else {}
    assigned, cohorts = _assignment_index(assignments)
    sources, attendance_counts = _attendance_index(attendance, cohorts)
    exports = set()

    def attended_assignment(session_id: str) -> dict:
        assignment = assigned.get(session_id)
        if assignment is None:
            raise ValueError(f"Evidence has an unassigned session_id {session_id}")
        if assignment["participant_id"] not in sources:
            raise ValueError(f"Session {session_id} has no participant attendance record")
        return assignment

    if session_studies is not None:
        for session_id, metadata in session_studies.items():
            assignment = attended_assignment(session_id)
            expected = {field: assignment[field] for field in _STUDY_FIELDS}
            if metadata != expected or type(metadata["order_index"]) is not int:
                raise ValueError(f"Export study metadata does not match assignment for session {session_id}")
            exports.add(session_id)

    def task_key(row: dict) -> tuple[str, str]:
        session_id = _text(row, "session_id")
        assignment = attended_assignment(session_id)
        if session_studies is not None and session_id not in session_studies:
            raise ValueError(f"No export metadata for session {session_id}")
        case_id = _text(row, "case_id")
        if case_id not in form_cases[assignment["form"]]:
            raise ValueError(f"Unassigned case_id {case_id} in session {session_id}")
        exports.add(session_id)
        return session_id, case_id

    seen_events = {}
    saved_stages = set()
    original_runs = {}
    bound_run_ids = set()
    for event in events:
        key = task_key(event)
        event_id = _text(event, "event_id")
        stage = _text(event, "stage")
        if event.get("outcome") not in _STAGE_OUTCOMES.get(stage, ()):
            raise ValueError(f"Invalid stage or outcome for event_id {event_id}")
        _elapsed_ms(event)
        if stage in ("predict", "transfer"):
            form = assigned[key[0]]["form"]
            question_key = "prediction" if stage == "predict" else "transfer"
            question = form_cases[form][key[1]].get(question_key)
            if not _registered_answer(event.get("answer"), question):
                raise ValueError(f"Invalid {stage} answer for event_id {event_id}")
        elif event.get("answer") is not None:
            raise ValueError(f"Unexpected answer for event_id {event_id}")
        if stage == "predict" and event.get("run_id") is not None:
            raise ValueError(f"A prediction cannot bind a run_id in event_id {event_id}")
        if event_id in seen_events:
            if event != seen_events[event_id]:
                raise ValueError(f"Conflicting records for event_id {event_id}")
            continue
        if stage in ("predict", "run", "transfer"):
            stage_key = (*key, stage)
            if stage_key in saved_stages:
                raise ValueError(f"Multiple {stage} records for {key[1]} in session {key[0]}")
            saved_stages.add(stage_key)
        if stage in ("run", "observe", "reflect", "transfer"):
            run_id = _text(event, "run_id")
            if stage == "run":
                if (*key, "predict") not in saved_stages:
                    raise ValueError(f"The original run lacks a preceding prediction in event_id {event_id}")
                original_runs[key] = run_id
            if stage == "transfer" and original_runs.get(key) != run_id:
                raise ValueError(f"Transfer must reference the preceding original run in event_id {event_id}")
            if stage in ("run", "observe"):
                if run_id in bound_run_ids:
                    raise ValueError(f"Duplicate run_id binding in event_id {event_id}")
                bound_run_ids.add(run_id)
        seen_events[event_id] = event

    calls = {}
    for call in tutor_calls:
        key = task_key(call)
        if key in calls:
            raise ValueError(f"Multiple tutor calls for {key[1]} in session {key[0]}")
        if _text(call, "run_id") != original_runs.get(key):
            raise ValueError(f"Tutor call must reference the original run for {key[1]} in session {key[0]}")
        status = call.get("status")
        if "status" not in call or (status is not None and (type(status) is not int or not 200 <= status <= 599)):
            raise ValueError(f"Invalid tutor status in session {key[0]}")
        recovered = status == 500 and call.get("error_code") == "tutor_interrupted"
        _elapsed_ms(call, allow_missing=status is None or recovered)
        if status == 200:
            _text(call.get("reply"), "explanation")
        elif call.get("reply") is not None:
            raise ValueError(f"Unexpected tutor reply without a successful status in session {key[0]}")
        calls[key] = call

    for session_id, case_id, stage in saved_stages:
        if stage == "transfer" and calls.get((session_id, case_id), {}).get("status") is None:
            raise ValueError(f"Transfer requires a terminal tutor call for {case_id} in session {session_id}")

    audits = {}
    for audit in feedback_audit:
        key = task_key(audit)
        if calls.get(key, {}).get("status") != 200:
            raise ValueError(f"Audit has no successful tutor reply for {key[1]} in session {key[0]}")
        if key in audits or audit.get("has_numeric_error") not in ("yes", "no"):
            raise ValueError(f"Invalid or duplicate numeric audit for {key[1]} in session {key[0]}")
        audits[key] = audit["has_numeric_error"] == "yes"

    sample_size = sum(attendance_counts["formal"]["human"].values())
    conditions = {}
    for condition in _CONDITIONS:
        sessions = {
            session_id for session_id, assignment in assigned.items()
            if assignment["condition"] == condition and assignment["cohort"] == "formal"
            and sources.get(assignment["participant_id"]) == "human"
        }
        tasks = sum(len(form_cases[assigned[session_id]["form"]]) for session_id in sessions)
        conditions[condition] = _condition_metrics(sessions, tasks, exports, seen_events.values(), calls, audits)
    status = "未测" if sample_size == 0 else "仅定性" if sample_size < 4 else "描述性比较"
    return {"status": status, "sample_size": sample_size, "attendance": attendance_counts, "conditions": conditions}


def _csv_rows(path: Path, fields: tuple[str, ...]) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if reader.fieldnames != list(fields):
            raise ValueError(f"Unexpected CSV header in {path}")
        rows = list(reader)
    if any(None in row or None in row.values() for row in rows):
        raise ValueError(f"Malformed CSV row in {path}")
    return rows


def _json_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key {key}")
        result[key] = value
    return result


def _invalid_json_constant(value: str):
    raise ValueError(f"Invalid JSON constant {value}")


def _json_value(path: Path):
    try:
        with path.open(encoding="utf-8-sig") as handle:
            return json.load(handle, object_pairs_hook=_json_object, parse_constant=_invalid_json_constant)
    except ValueError as error:
        raise ValueError(f"Invalid JSON in {path} ({error})") from error


def _session_exports(raw_dir: Path) -> tuple[list[dict], list[dict], dict]:
    events, calls, studies = [], [], {}
    for path in sorted(raw_dir.glob("*.json")):
        data = _json_value(path)
        session_id = _text(data, "session_id")
        if session_id != path.stem or session_id in studies:
            raise ValueError(f"Filename does not identify a unique export session in {path}")
        if set(data) != {"session_id", "study", "events", "runs", "cases", "tutor_calls"}:
            raise ValueError(f"Invalid export fields in {path}")
        rows, tutor_calls = data["events"], data["tutor_calls"]
        if not isinstance(rows, list) or not isinstance(tutor_calls, list) or not all(
            isinstance(data[field], dict) for field in ("runs", "cases", "study")
        ):
            raise ValueError(f"Invalid export structure in {path}")
        for event in rows:
            if _text(event, "session_id") != session_id:
                raise ValueError(f"Event belongs to another session in {path}")
            case_id = _text(event, "case_id")
            if _text(data["cases"].get(case_id), "case_id") != case_id:
                raise ValueError(f"Event case_id does not match the exported case in {path}")
            if event.get("run_id") is not None:
                run_id = _text(event, "run_id")
                if _text(data["runs"].get(run_id), "run_id") != run_id:
                    raise ValueError(f"Event run_id does not match the exported run in {path}")
        for call in tutor_calls:
            if not isinstance(call, dict) or set(call) != {"case_id", "run_id", "elapsed_ms", "status", "reply", "error_code"}:
                raise ValueError(f"Invalid tutor call in {path}")
            calls.append({**call, "session_id": session_id})
        events.extend(rows)
        studies[session_id] = data["study"]
    return events, calls, studies


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assignments", type=Path, default=_EVALUATION / "assignments.csv")
    parser.add_argument("--forms", type=Path, default=_EVALUATION / "forms.json")
    parser.add_argument("--raw-dir", type=Path, help="Session export directory (default evaluation/raw)")
    parser.add_argument("--attendance", type=Path, help="Attendance CSV (default raw-dir/attendance.csv)")
    parser.add_argument("--feedback-audit", type=Path, help="Optional audit CSV (default raw-dir/feedback_audit.csv)")
    args = parser.parse_args()
    raw_dir = args.raw_dir or _EVALUATION / "raw"
    attendance_path = args.attendance or raw_dir / "attendance.csv"
    audit_path = args.feedback_audit or raw_dir / "feedback_audit.csv"
    try:
        if (args.raw_dir is not None or raw_dir.exists()) and not raw_dir.is_dir():
            raise ValueError(f"Expected raw export directory {raw_dir}")
        events, calls, studies = _session_exports(raw_dir)
        report = analyze(
            events,
            assignments=_csv_rows(args.assignments, _ASSIGNMENT_FIELDS),
            forms=_json_value(args.forms),
            attendance=_csv_rows(attendance_path, _ATTENDANCE_FIELDS) if args.attendance or attendance_path.exists() else [],
            tutor_calls=calls,
            feedback_audit=_csv_rows(audit_path, _AUDIT_FIELDS) if args.feedback_audit or audit_path.exists() else [],
            session_studies=studies,
        )
    except (OSError, ValueError, csv.Error) as error:
        parser.error(str(error))
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
