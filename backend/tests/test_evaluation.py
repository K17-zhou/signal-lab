"""Exercise the analysis against the same records the evaluation collects."""

import csv
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from uuid import uuid4

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "evaluation" / "analyze.py"
FORMS = json.loads(SCRIPT.with_name("forms.json").read_text(encoding="utf-8"))
CASE_BY_ID = {case["case_id"]: case for cases in FORMS.values() for case in cases}
KEYS = json.loads((SCRIPT.parents[1] / "backend" / "content" / "study_keys.json").read_text(encoding="utf-8"))


def analyze(events, **kwargs):
    return run_path(str(SCRIPT))["analyze"](events, forms=FORMS, **kwargs)


def assignments(participant_id, cohort="formal"):
    orders = (
        (("B", "X"), ("C", "Y")),
        (("C", "X"), ("B", "Y")),
        (("B", "Y"), ("C", "X")),
        (("C", "Y"), ("B", "X")),
    )
    return [
        {
            "participant_id": participant_id,
            "session_id": str(uuid4()),
            "condition": condition,
            "form": form,
            "order_index": str(order_index),
            "cohort": cohort,
            "model_config": "frozen-model",
        }
        for order_index, (condition, form) in enumerate(orders[(int(participant_id[1:]) - 1) % 4], 1)
    ]


def attendance(participant_id, *, source="human", status="started"):
    return {"participant_id": participant_id, "source": source, "status": status}


def event(session, topic, stage, outcome, elapsed_ms, *, run_id=None, answer=None):
    return {
        "event_id": str(uuid4()),
        "session_id": session["session_id"],
        "case_id": f"study-{session['form'].lower()}-{topic}",
        "stage": stage,
        "run_id": run_id,
        "answer": answer,
        "note": "实验请求超时" if stage == "error" else None,
        "elapsed_ms": elapsed_ms,
        "outcome": outcome,
        "timestamp": "2026-11-08T10:30:00Z",
    }


def case_events(session, topic, outcome=None, elapsed_ms=2400):
    run_id = str(uuid4())
    case = CASE_BY_ID[f"study-{session['form'].lower()}-{topic}"]
    prediction = KEYS[case["prediction"]["question_id"]]["answer"]
    events = [
        event(session, topic, "predict", "recorded", 1800, answer=prediction),
        event(session, topic, "run", "completed", 25, run_id=run_id),
    ]
    if outcome is not None:
        question = case["transfer"]
        answer = dict(KEYS[question["question_id"]]["answer"])
        if outcome == "incorrect":
            if answer["kind"] == "numeric":
                answer["value"] += 1
            else:
                answer["option_id"] = next(
                    option["option_id"] for option in question["options"] if option["option_id"] != answer["option_id"]
                )
        events.append(event(session, topic, "transfer", outcome, elapsed_ms, run_id=run_id, answer=answer))
    return events


def tutor_call(run_event, status, elapsed_ms, *, condition="B"):
    run_id = run_event["run_id"]
    evidence = [{"run_id": run_id, "metric_key": "peak_frequency_hz"}] if condition == "C" else []
    return {
        "session_id": run_event["session_id"],
        "case_id": run_event["case_id"],
        "run_id": run_id,
        "status": status,
        "elapsed_ms": elapsed_ms,
        "reply": {"explanation": "请比较频谱主峰和理论频率。", "evidence": evidence,
                  "next_experiment": None, "misconception_code": None} if status == 200 else None,
        "error_code": "tutor_timeout" if status == 504 else None,
    }


def test_planned_pilot_teacher_and_synthetic_records_leave_formal_result_unmeasured():
    planned = assignments("S01")
    synthetic = assignments("S02")
    pilot = assignments("P01", "pilot")
    teacher = assignments("T01", "teacher")
    sessions = [synthetic[0], pilot[0], teacher[0]]
    tasks = [case_events(session, "safe", "correct") for session in sessions]
    result = analyze(
        [event for task in tasks for event in task],
        assignments=planned + synthetic + pilot + teacher,
        attendance=[attendance("S02", source="synthetic"), attendance("P01"), attendance("T01")],
        tutor_calls=[tutor_call(task[1], 200, 1200, condition=session["condition"])
                     for task, session in zip(tasks, sessions, strict=True)],
    )
    assert result["status"] == "未测"
    assert result["sample_size"] == 0
    assert result["attendance"]["formal"]["synthetic"]["started"] == 1
    assert result["attendance"]["pilot"]["human"]["started"] == 1
    assert result["attendance"]["teacher"]["human"]["started"] == 1
    assert result["conditions"]["B"]["completion_rate"] is None
    assert result["conditions"]["C"]["assigned_tasks"] == 0


def test_wrong_submissions_complete_tasks_and_missing_exports_keep_their_denominator():
    first = assignments("S01")
    stopped = assignments("S02")
    correct = case_events(first[0], "safe", "correct", 1400)
    incorrect = case_events(first[0], "boundary", "incorrect", 2200)
    prediction, _ = case_events(first[0], "alias")
    error = event(first[0], "alias", "error", "failed", 5000)
    result = analyze(
        correct + incorrect + [prediction, error, dict(correct[-1]), dict(error)],
        assignments=first + stopped,
        attendance=[attendance("S01"), attendance("S02", status="stopped")],
        tutor_calls=[tutor_call(correct[1], 200, 1200), tutor_call(incorrect[1], 504, 30000)],
    )
    assert result["status"] == "仅定性"
    assert result["sample_size"] == 2
    assert result["attendance"]["formal"]["human"]["stopped"] == 1
    b, c = (result["conditions"][condition] for condition in ("B", "C"))
    assert b["assigned_tasks"] == c["assigned_tasks"] == 6
    assert b["completed_tasks"] == 2
    assert (b["transfer_correct"], b["transfer_incorrect"], b["incomplete_tasks"]) == (1, 1, 4)
    assert b["completion_rate"] == pytest.approx(1 / 3)
    assert (b["stage_errors"], b["missing_exports"], c["missing_exports"]) == (1, 1, 2)
    assert b["tutor"]["failures"] == 1
    assert c["incomplete_tasks"] == 6
    assert b["elapsed_ms_by_stage"]["transfer"] == {"n": 2, "min": 1400, "median": 1800, "max": 2200}
    assert c["elapsed_ms_by_stage"]["transfer"]["median"] is None


def test_duplicate_event_id_with_different_content_stops_analysis():
    assigned = assignments("S01")
    events = case_events(assigned[0], "safe", "correct")
    conflict = {**events[-1], "outcome": "incorrect"}
    with pytest.raises(ValueError, match="event_id"):
        analyze(events + [conflict], assignments=assigned, attendance=[attendance("S01")])


def test_duplicate_event_id_cannot_hide_an_invalid_answer_type():
    assigned = assignments("S01")
    events = case_events(assigned[0], "safe", "correct")
    events[0]["answer"] = {"kind": "numeric", "value": 1, "unit": "Hz"}
    malformed = {**events[0], "answer": {**events[0]["answer"], "value": True}}
    with pytest.raises(ValueError, match="predict answer|event_id"):
        analyze(events + [malformed], assignments=assigned, attendance=[attendance("S01")],
                tutor_calls=[tutor_call(events[1], 200, 1200)])


def test_events_for_an_unattended_slot_cannot_establish_a_human_sample():
    assigned = assignments("S01")
    with pytest.raises(ValueError, match="attendance"):
        analyze(case_events(assigned[0], "safe", "correct"), assignments=assigned, attendance=[])


def test_conflicting_attendance_sources_cannot_promote_synthetic_records():
    with pytest.raises(ValueError, match="attendance"):
        analyze(
            [],
            assignments=assignments("S01"),
            attendance=[attendance("S01", source="synthetic"), attendance("S01")],
        )


def test_an_assignment_must_include_both_periods_before_it_can_supply_denominators():
    with pytest.raises(ValueError, match="period"):
        analyze([], assignments=assignments("S01")[:1], attendance=[attendance("S01")])


def test_events_from_the_other_form_are_rejected():
    assigned = assignments("S01")
    events = case_events(assigned[0], "safe", "correct")
    with pytest.raises(ValueError, match="case_id"):
        analyze([{**events[0], "case_id": "study-y-safe"}], assignments=assigned, attendance=[attendance("S01")])


@pytest.mark.parametrize("order", [(2,), (1, 2), (0, 2, 1), (1, 0, 2)])
def test_transfer_requires_the_preceding_prediction_and_original_run(order):
    assigned = assignments("S01")
    events = case_events(assigned[0], "safe", "correct")
    with pytest.raises(ValueError, match="prediction|original run"):
        analyze(
            [events[index] for index in order],
            assignments=assigned,
            attendance=[attendance("S01")],
            tutor_calls=[tutor_call(events[1], 200, 1200)] if 1 in order else [],
        )


@pytest.mark.parametrize("row", ["transfer", "tutor"])
def test_transfer_and_tutor_call_must_reference_original_run_even_after_observation(row):
    assigned = assignments("S01")
    prediction, run, transfer = case_events(assigned[1], "safe", "correct")
    observation = event(assigned[1], "safe", "observe", "completed", 30, run_id=str(uuid4()))
    call = tutor_call(run, 200, 1200, condition="C")
    referenced = transfer if row == "transfer" else call
    referenced["run_id"] = observation["run_id"]
    with pytest.raises(ValueError, match="original run"):
        analyze([prediction, run, observation, transfer], assignments=assigned,
                attendance=[attendance("S01")], tutor_calls=[call])


@pytest.mark.parametrize("status", ["absent", None, 100])
def test_transfer_requires_a_terminal_tutor_call(status):
    assigned = assignments("S01")
    events = case_events(assigned[0], "safe", "correct")
    calls = [] if status == "absent" else [tutor_call(events[1], status, None if status is None else 500)]
    with pytest.raises(ValueError, match="terminal tutor|tutor status"):
        analyze(events, assignments=assigned, attendance=[attendance("S01")], tutor_calls=calls)


@pytest.mark.parametrize(("topic", "answer"), [
    ("safe", {}),
    ("safe", {"kind": "numeric", "value": True, "unit": "Hz"}),
    ("safe", {"kind": "numeric", "value": float("nan"), "unit": "Hz"}),
    ("safe", {"kind": "numeric", "value": 44.0, "unit": "ratio"}),
    ("boundary", {"kind": "choice", "option_id": "unregistered"}),
    ("boundary", {"kind": "numeric", "value": 1.0, "unit": "Hz"}),
])
def test_transfer_answer_must_match_frozen_question(topic, answer):
    assigned = assignments("S01")
    events = case_events(assigned[0], topic, "correct")
    events[-1]["answer"] = answer
    with pytest.raises(ValueError, match="transfer answer"):
        analyze(events, assignments=assigned, attendance=[attendance("S01")],
                tutor_calls=[tutor_call(events[1], 200, 1200)])


@pytest.mark.parametrize(("fields", "message"), [
    ({"answer": {"kind": "choice", "option_id": "near-zero"}}, "predict answer"),
    ({"run_id": str(uuid4())}, "prediction.*run_id"),
])
def test_a_malformed_prediction_cannot_serve_as_a_transfer_prerequisite(fields, message):
    assigned = assignments("S01")
    events = case_events(assigned[0], "safe", "correct")
    events[0].update(fields)
    with pytest.raises(ValueError, match=message):
        analyze(events, assignments=assigned, attendance=[attendance("S01")],
                tutor_calls=[tutor_call(events[1], 200, 1200)])


def test_original_run_id_cannot_be_bound_to_two_cases():
    assigned = assignments("S01")
    safe = case_events(assigned[0], "safe", "correct")
    alias = case_events(assigned[0], "alias", "correct")
    alias[1]["run_id"] = alias[2]["run_id"] = safe[1]["run_id"]
    with pytest.raises(ValueError, match="run_id"):
        analyze(safe + alias, assignments=assigned, attendance=[attendance("S01")],
                tutor_calls=[tutor_call(safe[1], 200, 1200), tutor_call(alias[1], 200, 1200)])


def test_tutor_audit_uses_only_reviewed_successes_and_preserves_failures():
    assigned = assignments("S01")
    b_safe = case_events(assigned[0], "safe")
    b_alias = case_events(assigned[0], "alias")
    b_boundary = case_events(assigned[0], "boundary")
    c_safe = case_events(assigned[1], "safe")
    calls = [
        tutor_call(b_safe[1], 200, 1234),
        tutor_call(b_alias[1], 200, 1566),
        tutor_call(b_boundary[1], 504, 12000),
        tutor_call(c_safe[1], None, None),
    ]
    review = {"session_id": assigned[0]["session_id"], "case_id": "study-x-safe", "has_numeric_error": "yes"}
    result = analyze(
        b_safe + b_alias + b_boundary + c_safe,
        assignments=assigned,
        attendance=[attendance("S01")],
        tutor_calls=calls,
        feedback_audit=[review],
    )
    b, c = (result["conditions"][condition]["tutor"] for condition in ("B", "C"))
    assert (b["calls"], b["successes"], b["failures"], b["interrupted"]) == (3, 2, 1, 0)
    assert (c["calls"], c["successes"], c["failures"], c["interrupted"]) == (1, 0, 0, 1)
    assert b["audit"] == {"audited_replies": 1, "missing_audits": 1, "numeric_errors": 1}
    assert b["elapsed_ms"] == {"n": 3, "min": 1234, "median": 1566, "max": 12000}
    assert c["elapsed_ms"]["n"] == 0
    assert result["conditions"]["C"]["incomplete_tasks"] == 3


def test_tutor_audit_for_a_failed_call_is_rejected():
    assigned = assignments("S01")
    events = case_events(assigned[0], "safe")
    review = {"session_id": assigned[0]["session_id"], "case_id": "study-x-safe", "has_numeric_error": "no"}
    with pytest.raises(ValueError, match="successful"):
        analyze(
            events,
            assignments=assigned,
            attendance=[attendance("S01")],
            tutor_calls=[tutor_call(events[1], 504, 12000)],
            feedback_audit=[review],
        )


def test_recovered_tutor_failure_counts_without_an_unobserved_latency():
    assigned = assignments("S01")
    events = case_events(assigned[0], "safe")
    call = {**tutor_call(events[1], 500, None), "error_code": "tutor_interrupted"}
    result = analyze(
        events, assignments=assigned, attendance=[attendance("S01")], tutor_calls=[call],
    )
    tutor = result["conditions"]["B"]["tutor"]
    assert (tutor["calls"], tutor["failures"], tutor["elapsed_ms"]["n"]) == (1, 1, 0)


def test_four_formal_starters_permit_a_descriptive_report():
    participants = ["S01", "S02", "S03", "S04"]
    result = analyze(
        [],
        assignments=[row for participant in participants for row in assignments(participant)],
        attendance=[attendance(participant) for participant in participants],
    )
    assert result["status"] == "描述性比较"
    assert result["sample_size"] == 4
    assert result["conditions"]["B"]["incomplete_tasks"] == 12


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def test_cli_cross_checks_export_assignment_metadata_and_writes_no_report_file(tmp_path):
    assigned = assignments("S01")
    first = assigned[0]
    session_id = first["session_id"]
    assignment_path = tmp_path / "planned.csv"
    forms_path = tmp_path / "forms.json"
    raw = tmp_path / "raw"
    raw.mkdir()
    write_csv(assignment_path, assigned)
    write_csv(raw / "attendance.csv", [attendance("S01")])
    forms_path.write_text(json.dumps(FORMS), encoding="utf-8")
    export = {
        "session_id": session_id,
        "study": {"condition": "B", "form": "X", "order_index": 1, "cohort": "formal", "model_config": "frozen-model"},
        "events": [], "runs": {}, "cases": {}, "tutor_calls": [],
    }
    session_path = raw / f"{session_id}.json"
    session_path.write_text(json.dumps(export), encoding="utf-8")
    command = [
        sys.executable, "-X", "utf8", str(SCRIPT), "--assignments", str(assignment_path),
        "--forms", str(forms_path), "--raw-dir", str(raw),
    ]
    before = set(tmp_path.rglob("*"))
    completed = subprocess.run(command, cwd=tmp_path, capture_output=True, encoding="utf-8", check=False)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "仅定性"
    assert result["conditions"]["B"]["missing_exports"] == 0
    assert result["conditions"]["C"]["missing_exports"] == 1
    assert set(tmp_path.rglob("*")) == before

    export["study"]["condition"] = "C"
    session_path.write_text(json.dumps(export), encoding="utf-8")
    conflict = subprocess.run(command, cwd=tmp_path, capture_output=True, encoding="utf-8", check=False)
    assert conflict.returncode != 0
    assert "study metadata" in conflict.stderr
    assert not conflict.stdout
