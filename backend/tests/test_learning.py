"""Learning records survive retries and remain scoped to their session."""

from concurrent.futures import ThreadPoolExecutor
import csv
from io import StringIO
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.learning import score_answer
from app.schemas import NumericAnswer


CASE = "alias-frequency"
PARAMS = {"frequency_hz": 70, "sample_rate_hz": 110}


def numeric(value, unit="Hz"):
    return {"kind": "numeric", "value": value, "unit": unit}


def event(session, stage, *, case=CASE, **fields):
    return {
        "event_id": str(uuid4()),
        "session_id": session,
        "case_id": case,
        "stage": stage,
        "elapsed_ms": 1200,
        **fields,
    }


def append(client, payload):
    response = client.post("/api/events", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def compute(client, params=PARAMS):
    response = client.post(
        "/api/experiments/run",
        json={"experiment_type": "sampling_aliasing", "params": params},
    )
    assert response.status_code == 200
    return response.json()["run_id"]


def start_case(client, session, *, case=CASE, params=PARAMS, prediction=None):
    append(client, event(session, "predict", case=case, answer=prediction or numeric(30)))
    run_id = compute(client, params)
    append(client, event(session, "run", case=case, run_id=run_id))
    return run_id


def history(client, session):
    response = client.get(f"/api/sessions/{session}/events")
    assert response.status_code == 200
    return response.json()["events"]


def test_prediction_survives_restart_and_exact_retry(tmp_path):
    database = tmp_path / "lab.sqlite3"
    session = str(uuid4())
    prediction = event(session, "predict", answer=numeric(22))
    with TestClient(create_app(database)) as client:
        original = append(client, prediction)
    with TestClient(create_app(database)) as client:
        assert append(client, prediction) == original
        assert client.post("/api/events", json={**prediction, "answer": numeric(30)}).status_code == 409
        second = event(session, "predict", answer=numeric(30))
        assert client.post("/api/events", json=second).status_code == 409
        assert history(client, session) == [original]
        assert original["answer"] == numeric(22)
        assert original["run_id"] is None


def test_concurrent_prediction_submissions_keep_one_original(tmp_path):
    database = tmp_path / "lab.sqlite3"
    session = str(uuid4())
    first = event(session, "predict", answer=numeric(22))
    second = event(session, "predict", answer=numeric(30))
    with TestClient(create_app(database)) as left, TestClient(create_app(database)) as right:
        with ThreadPoolExecutor(max_workers=2) as pool:
            left_result = pool.submit(left.post, "/api/events", json=first)
            right_result = pool.submit(right.post, "/api/events", json=second)
            responses = [left_result.result(), right_result.result()]
        assert sorted(response.status_code for response in responses) == [200, 409]
        winner = next(response.json() for response in responses if response.status_code == 200)
        assert history(left, session) == [winner]


def test_a_run_must_match_the_case_and_belong_to_the_session(tmp_path):
    first, second = str(uuid4()), str(uuid4())
    with TestClient(create_app(tmp_path / "lab.sqlite3")) as client:
        run_id = compute(client)
        without_prediction = event(first, "run", run_id=run_id)
        assert client.post("/api/events", json=without_prediction).status_code == 409
        append(client, event(first, "predict", answer=numeric(40)))
        missing = event(first, "run", run_id=str(uuid4()))
        assert client.post("/api/events", json=missing).status_code == 404
        wrong = event(first, "run", run_id=compute(client, {"frequency_hz": 70, "sample_rate_hz": 100}))
        assert client.post("/api/events", json=wrong).status_code == 422
        append(client, without_prediction)
        append(client, event(second, "predict", answer=numeric(40)))
        transfer = event(second, "transfer", run_id=run_id, answer=numeric(30))
        assert client.post("/api/events", json=transfer).status_code == 409
        copied_run = event(second, "run", run_id=run_id)
        assert client.post("/api/events", json=copied_run).status_code == 409
        assert [row["stage"] for row in history(client, second)] == ["predict"]


@pytest.mark.parametrize(("answer", "status", "outcome"), [
    (numeric(30.5), 200, "correct"),
    (numeric(30.6), 200, "incorrect"),
    (numeric(30, "kHz"), 422, None),
])
def test_transfer_grades_only_valid_hz_answers(tmp_path, answer, status, outcome):
    session = str(uuid4())
    with TestClient(create_app(tmp_path / "lab.sqlite3")) as client:
        run_id = start_case(client, session)
        payload = event(session, "transfer", run_id=run_id, answer=answer)
        response = client.post("/api/events", json=payload)
        assert response.status_code == status
        if outcome is None:
            assert len(history(client, session)) == 2
        else:
            assert response.json()["outcome"] == outcome
            assert append(client, payload) == response.json()
            assert client.post("/api/events", json={**payload, "event_id": str(uuid4())}).status_code == 409


@pytest.mark.parametrize(("option_id", "outcome"), [("not-guaranteed", "correct"), ("always", "incorrect")])
def test_choice_is_graded_by_option_identifier(tmp_path, option_id, outcome):
    session = str(uuid4())
    with TestClient(create_app(tmp_path / "lab.sqlite3")) as client:
        run_id = start_case(
            client, session, case="nyquist-boundary",
            params={"frequency_hz": 50, "sample_rate_hz": 100},
            prediction={"kind": "choice", "option_id": "always"},
        )
        saved = append(client, event(
            session, "transfer", case="nyquist-boundary", run_id=run_id,
            answer={"kind": "choice", "option_id": option_id},
        ))
        assert saved["outcome"] == outcome


def test_exports_keep_real_events_and_multiline_reflection_in_one_session(tmp_path):
    session, other = str(uuid4()), str(uuid4())
    note = "采样点落在零附近，\n需要检查原始频率。"
    with TestClient(create_app(tmp_path / "lab.sqlite3")) as client:
        run_id = start_case(client, session)
        reflection = append(client, event(session, "reflect", run_id=run_id, note=note))
        assert reflection["outcome"] == "recorded"
        assert reflection["answer"] is None
        append(client, event(session, "transfer", run_id=run_id, answer=numeric(36)))
        append(client, event(session, "error", note="计算超时"))
        append(client, event(other, "predict", answer=numeric(88)))
        url = f"/api/sessions/{session}/export"
        exported = client.get(url, params={"format": "json"})
        assert exported.status_code == 200
        rows = exported.json()["events"]
        assert rows == history(client, session)
        assert [(row["stage"], row["outcome"]) for row in rows] == [
            ("predict", "recorded"), ("run", "completed"), ("reflect", "recorded"),
            ("transfer", "incorrect"), ("error", "failed"),
        ]
        assert all(row["session_id"] == session and row["elapsed_ms"] == 1200 for row in rows)
        assert rows[1]["run_id"] == run_id
        assert rows[3]["answer"] == numeric(36)
        assert exported.json()["runs"][run_id]["metrics"]["peak_frequency_hz"] == pytest.approx(40)
        assert exported.json()["cases"][CASE]["transfer"]["params"]["frequency_hz"] == 80
        exported_csv = client.get(url, params={"format": "csv"})
        assert exported_csv.status_code == 200
        csv_rows = list(csv.DictReader(StringIO(exported_csv.content.decode("utf-8-sig"))))
        assert [row["event_id"] for row in csv_rows] == [row["event_id"] for row in rows]
        assert csv_rows[2]["note"] == note
        assert csv_rows[3]["answer_value"] == "36.0"
        assert csv_rows[3]["question_id"] == "alias-transfer"
        assert csv_rows[3]["question_prompt"] == exported.json()["cases"][CASE]["transfer"]["prompt"]
        assert json.loads(csv_rows[3]["question_params"])["frequency_hz"] == 80
        assert json.loads(csv_rows[3]["run_params"])["frequency_hz"] == 70


def test_public_catalog_has_new_transfer_parameters_and_no_answer_keys(tmp_path):
    with TestClient(create_app(tmp_path / "lab.sqlite3")) as client:
        response = client.get("/api/learning/cases")
        assert response.status_code == 200
        cases = response.json()
        assert len(cases) == 7
        for case in cases:
            assert case["prediction"]["params"] != case["transfer"]["params"]
            for question in (case["prediction"], case["transfer"]):
                assert set(question) <= {"question_id", "prompt", "params", "kind", "unit", "options"}
                assert "answer" not in question
                for option in question.get("options", []):
                    assert set(option) == {"option_id", "label"}


def test_filter_transfer_scores_a_ratio_and_preserves_the_real_run(tmp_path):
    session = str(uuid4())
    case = "lowpass-gain"
    with TestClient(create_app(tmp_path / "lab.sqlite3")) as client:
        prediction = event(session, "predict", case=case, answer=numeric(0.4, "ratio"))
        assert append(client, prediction)["outcome"] == "recorded"
        response = client.post("/api/experiments/run", json={
            "experiment_type": "lowpass_filter", "params": {"cutoff_hz": 60},
        })
        assert response.status_code == 200, response.text
        run_id = response.json()["run_id"]
        append(client, event(session, "run", case=case, run_id=run_id))
        wrong_unit = event(session, "transfer", case=case, run_id=run_id, answer=numeric(0.28))
        assert client.post("/api/events", json=wrong_unit).status_code == 422
        answer = event(session, "transfer", case=case, run_id=run_id, answer=numeric(0.28, "ratio"))
        assert append(client, answer)["outcome"] == "correct"
        export = client.get(f"/api/sessions/{session}/export").json()
        assert export["events"][-1]["answer"] == numeric(0.28, "ratio")
        assert export["cases"][case]["transfer"]["params"] == {"cutoff_hz": 90}
        assert export["runs"][run_id]["metrics"]["gain_120hz"] == pytest.approx(0.05380920, abs=0.005)


@pytest.mark.parametrize(("value", "correct"), [
    (0.25845479, True),
    (0.29845479, True),
    (0.25845478, False),
    (0.29845480, False),
])
def test_filter_scoring_includes_exact_decimal_tolerance_bounds(value, correct):
    result = score_answer("lowpass-gain-transfer", NumericAnswer(kind="numeric", value=value, unit="ratio"))
    assert result.correct is correct
