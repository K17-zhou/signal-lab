"""Assigned learning sessions keep their form, condition and guidance budget."""

import csv
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import StudyTutorCall


class StudyModel:
    def __init__(self):
        self.contexts = []
        self.timeout = False

    def complete(self, context):
        self.contexts.append(context)
        if self.timeout:
            raise TimeoutError
        if context["mode"] == "B":
            return "对照实验记录，核对观测主峰。"
        run = context["run"]
        return json.dumps({
            "focus": "sampling",
            "evidence": [{"run_id": run["run_id"], "metric_key": "peak_frequency_hz"}],
            "next_experiment": {
                "experiment_type": "sampling_aliasing",
                "params": {**run["params"], "sample_rate_hz": 400},
            },
        })


@pytest.fixture
def study_files(tmp_path, monkeypatch):
    sessions = {mode: str(uuid4()) for mode in ("B", "C")}
    path = tmp_path / "assignments.csv"
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(("participant_id", "session_id", "condition", "form", "order_index", "cohort", "model_config"))
        writer.writerow(("S01", sessions["B"], "B", "X", 1, "formal", "test-fixture"))
        writer.writerow(("S01", sessions["C"], "C", "Y", 2, "formal", "test-fixture"))
    monkeypatch.setenv("SIGNAL_LAB_STUDY_ASSIGNMENTS", str(path))
    return tmp_path / "study.sqlite3", path, sessions


@pytest.fixture
def study(study_files):
    database, _, sessions = study_files
    model = StudyModel()
    with TestClient(create_app(database, tutor_client=model)) as client:
        yield client, model, sessions


def post_event(client, session, case, stage, **fields):
    return client.post("/api/events", json={
        "event_id": str(uuid4()), "session_id": session, "case_id": case,
        "stage": stage, "elapsed_ms": 15, **fields,
    })


def compute(client, params):
    response = client.post("/api/experiments/run", json={
        "experiment_type": "sampling_aliasing", "params": params,
    })
    assert response.status_code == 200, response.text
    return response.json()


def start_case(client, session):
    state = client.get(f"/api/evaluation/sessions/{session}")
    assert state.status_code == 200, state.text
    case = state.json()["cases"][0]
    case_id = case["case_id"]
    assert post_event(client, session, case_id, "predict",
                      answer={"kind": "numeric", "value": 20, "unit": "Hz"}).status_code == 200
    run = compute(client, case["prediction"]["params"])
    assert post_event(client, session, case_id, "run", run_id=run["run_id"]).status_code == 200
    return case, run


def transfer(client, session, case, run):
    return post_event(client, session, case["case_id"], "transfer", run_id=run["run_id"],
                      answer={"kind": "numeric", "value": case["transfer"]["params"]["frequency_hz"], "unit": "Hz"})


def test_frozen_session_has_only_its_three_cases_without_keys(study):
    client, _, sessions = study
    response = client.get(f"/api/evaluation/sessions/{sessions['B']}")
    assert response.status_code == 200
    data = response.json()
    assert data["study"] == {"condition": "B", "form": "X", "order_index": 1,
                             "cohort": "formal", "model_config": "test-fixture"}
    assert [case["case_id"] for case in data["cases"]] == ["study-x-safe", "study-x-alias", "study-x-boundary"]
    assert "answer" not in data["cases"][0]["transfer"]
    assert data["events"] == data["tutor_calls"] == []
    assert client.get(f"/api/evaluation/sessions/{uuid4()}").status_code == 404
    assert all(not case["case_id"].startswith("study-") for case in client.get("/api/learning/cases").json())
    bad = post_event(client, sessions["B"], "study-y-safe", "predict",
                     answer={"kind": "numeric", "value": 20, "unit": "Hz"})
    assert bad.status_code == 404


def test_b_replays_one_plain_attempt_and_records_timing(study):
    client, model, sessions = study
    session = sessions["B"]
    case, run = start_case(client, session)
    request = {"session_id": session, "run_id": run["run_id"], "message": "临时客户端输入"}
    assert transfer(client, session, case, run).status_code == 409
    assert client.post("/api/tutor/guide", json={**request, "mode": "C"}).status_code == 409
    assert not model.contexts
    first = client.post("/api/tutor/guide", json={**request, "mode": "B"})
    assert first.status_code == 200, first.text
    assert first.json()["evidence"] == [] and first.json()["next_experiment"] is None
    assert client.post("/api/tutor/guide", json={**request, "mode": "B"}).json() == first.json()
    assert len(model.contexts) == 1
    assert model.contexts[0]["run"]["params"] == run["params"]
    assert model.contexts[0]["run"]["metrics"] == run["metrics"]
    assert model.contexts[0]["message"] != request["message"]
    assert "transfer" not in model.contexts[0]["exercise"]
    graded = transfer(client, session, case, run)
    assert graded.status_code == 200 and graded.json()["outcome"] == "correct"
    exported = client.get(f"/api/sessions/{session}/export").json()
    assert exported["study"]["condition"] == "B"
    call, = exported["tutor_calls"]
    assert call["status"] == 200 and call["reply"] == first.json() and call["elapsed_ms"] >= 0
    assert client.get(f"/api/evaluation/sessions/{session}").json()["tutor_calls"] == [call]


def test_c_can_confirm_only_the_saved_proposal_once(study):
    client, _, sessions = study
    session = sessions["C"]
    case, run = start_case(client, session)
    request = {"session_id": session, "run_id": run["run_id"], "message": "解释实验", "mode": "C"}
    unmatched = compute(client, {**run["params"], "sample_rate_hz": 500})
    assert post_event(client, session, case["case_id"], "observe", run_id=unmatched["run_id"]).status_code == 409
    response = client.post("/api/tutor/guide", json=request)
    assert response.status_code == 200, response.text
    comparison = compute(client, response.json()["next_experiment"]["params"])
    assert post_event(client, session, case["case_id"], "observe", run_id=unmatched["run_id"]).status_code == 409
    assert post_event(client, session, case["case_id"], "observe", run_id=comparison["run_id"]).status_code == 200
    second = compute(client, comparison["params"])
    assert post_event(client, session, case["case_id"], "observe", run_id=second["run_id"]).status_code == 409
    assert transfer(client, session, case, run).status_code == 200


def test_timeout_is_preserved_and_allows_the_transfer(study):
    client, model, sessions = study
    model.timeout = True
    session = sessions["B"]
    case, run = start_case(client, session)
    request = {"session_id": session, "run_id": run["run_id"], "message": "解释", "mode": "B"}
    for _ in range(2):
        result = client.post("/api/tutor/guide", json=request)
        assert result.status_code == 504 and result.json()["detail"] == "tutor_timeout"
    assert len(model.contexts) == 1
    call, = client.get(f"/api/evaluation/sessions/{session}").json()["tutor_calls"]
    assert call["status"] == 504 and call["reply"] is None and call["elapsed_ms"] >= 0
    assert transfer(client, session, case, run).status_code == 200


def test_study_database_rejects_missing_or_changed_assignments(study_files, monkeypatch):
    database, path, sessions = study_files
    with TestClient(create_app(database, tutor_client=StudyModel())) as client:
        start_case(client, sessions["B"])
    monkeypatch.delenv("SIGNAL_LAB_STUDY_ASSIGNMENTS")
    with pytest.raises(RuntimeError, match="original study assignments"):
        with TestClient(create_app(database, tutor_client=StudyModel())):
            pass
    monkeypatch.setenv("SIGNAL_LAB_STUDY_ASSIGNMENTS", str(path))
    path.write_text(path.read_text(encoding="utf-8").replace("test-fixture", "changed-model"), encoding="utf-8")
    with pytest.raises(RuntimeError, match="original study assignments"):
        with TestClient(create_app(database, tutor_client=StudyModel())):
            pass


def test_study_database_refuses_a_second_active_service(study_files):
    database, _, sessions = study_files
    with TestClient(create_app(database, tutor_client=StudyModel())) as first:
        with pytest.raises(RuntimeError, match="already active"):
            with TestClient(create_app(database, tutor_client=StudyModel())):
                pass
        assert first.get(f"/api/evaluation/sessions/{sessions['B']}").status_code == 200
    with TestClient(create_app(database, tutor_client=StudyModel())) as restarted:
        assert restarted.get(f"/api/evaluation/sessions/{sessions['B']}").status_code == 200


def test_pending_guidance_cannot_be_exported_until_recovery(study_files):
    database, _, sessions = study_files
    session = sessions["B"]
    url = f"/api/sessions/{session}/export"
    with TestClient(create_app(database, tutor_client=StudyModel())) as client:
        case, run = start_case(client, session)
        call = StudyTutorCall(case_id=case["case_id"], run_id=run["run_id"])
        assert client.app.state.store.reserve_study_tutor_call(session, call)
        assert client.get(url).status_code == 409
    with TestClient(create_app(database, tutor_client=StudyModel())) as restarted:
        response = restarted.get(url)
        assert response.status_code == 200
        recovered, = response.json()["tutor_calls"]
        assert recovered["status"] == 500 and recovered["error_code"] == "tutor_interrupted"
        assert recovered["elapsed_ms"] is None
        assert transfer(restarted, session, case, run).status_code == 200


def test_holdout_i09_withholds_transfer_parameters_from_guidance(study):
    client, model, sessions = study
    session = sessions["C"]
    state = client.get(f"/api/evaluation/sessions/{session}").json()
    assert state["study"]["form"] == "Y"
    case = next(case for case in state["cases"] if case["case_id"] == "study-y-boundary")
    case_id = case["case_id"]
    prediction = {"kind": "choice", "option_id": "near-zero"}
    saved = post_event(client, session, case_id, "predict", answer=prediction)
    assert saved.status_code == 200
    run = compute(client, case["prediction"]["params"])
    assert post_event(client, session, case_id, "run", run_id=run["run_id"]).status_code == 200

    def propose_transfer(context):
        assert set(context) == {"run", "prediction", "exercise", "theory", "message", "mode"}
        assert context["run"] == {key: value for key, value in run.items() if key != "series"}
        assert context["prediction"] == prediction
        assert context["exercise"] == {
            "title": case["title"],
            "goal": case["goal"],
            **{key: case["prediction"][key] for key in ("prompt", "params", "options")},
        }
        serialized = json.dumps(context, ensure_ascii=False, sort_keys=True)
        assert case["transfer"]["question_id"] not in serialized
        assert case["transfer"]["prompt"] not in serialized
        assert json.dumps(case["transfer"]["params"], sort_keys=True) not in serialized
        assert json.dumps({"kind": "choice", "option_id": "alternating"}, sort_keys=True) not in serialized
        return json.dumps({
            "focus": "phase",
            "evidence": [{"run_id": run["run_id"], "metric_key": "sample_rms"}],
            "next_experiment": {"experiment_type": "sampling_aliasing", "params": case["transfer"]["params"]},
        })

    model.complete = propose_transfer
    guide = client.post("/api/tutor/guide", json={
        "session_id": session, "run_id": run["run_id"], "message": "解释边界相位", "mode": "C",
    })
    assert guide.status_code == 200 and guide.json()["next_experiment"] is None
    duplicate = compute(client, case["transfer"]["params"])
    assert post_event(client, session, case_id, "observe", run_id=duplicate["run_id"]).status_code == 409
    restored = client.get(f"/api/evaluation/sessions/{session}").json()
    assert restored["study"]["form"] == "Y"
    assert [event["stage"] for event in restored["events"]] == ["predict", "run"]
    assert restored["events"][0] == saved.json()
