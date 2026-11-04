"""AI explanations may cite only data from the saved run."""

import json
import time
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.main import create_app


class ModelStub:
    def __init__(self):
        self.contexts = []
        self.change = {}
        self.raw = None
        self.delay = 0

    def complete(self, context):
        self.contexts.append(context)
        time.sleep(self.delay)
        if self.raw is not None:
            return self.raw
        return json.dumps({
            "explanation": "采样频率不足时，原信号和折叠后的信号会产生相同样本。",
            "evidence": [{"run_id": context["run"]["run_id"], "metric_key": "peak_frequency_hz"}],
            "next_experiment": {
                "experiment_type": "sampling_aliasing",
                "params": {"frequency_hz": 70, "sample_rate_hz": 200},
            },
            "misconception_code": None,
            **self.change,
        })


def start_run(client, frequency=70, rate=110):
    result = client.post("/api/experiments/run", json={
        "experiment_type": "sampling_aliasing",
        "params": {"frequency_hz": frequency, "sample_rate_hz": rate},
    })
    assert result.status_code == 200
    return result.json()["run_id"]


def event(client, session_id, stage, **fields):
    return client.post("/api/events", json={
        "event_id": str(uuid4()), "session_id": session_id,
        "case_id": "alias-frequency", "stage": stage, "elapsed_ms": 10,
        **fields,
    })


@pytest.fixture()
def tutoring(tmp_path):
    model = ModelStub()
    session = str(uuid4())
    with TestClient(create_app(tmp_path / "tutor.sqlite3", tutor_client=model)) as client:
        prediction = {"kind": "numeric", "value": 22, "unit": "Hz"}
        assert event(client, session, "predict", answer=prediction).status_code == 200
        run = start_run(client)
        assert event(client, session, "run", run_id=run).status_code == 200
        yield client, model, {"session_id": session, "run_id": run, "message": "为什么有混叠？"}


def test_context_uses_saved_prediction_and_has_no_answer_keys(tutoring):
    client, model, request = tutoring
    response = client.post("/api/tutor/guide", json={
        **request, "prediction": {"kind": "numeric", "value": 999, "unit": "Hz"},
    })
    assert response.status_code == 200
    result = response.json()
    assert result["evidence"] == [{"run_id": request["run_id"], "metric_key": "peak_frequency_hz"}]
    assert result["next_experiment"]["params"]["sample_rate_hz"] == 200
    context = model.contexts[0]
    assert context["prediction"] == {"kind": "numeric", "value": 22.0, "unit": "Hz"}
    assert context["run"]["metrics"]["peak_frequency_hz"] == pytest.approx(40)
    assert set(context) == {"run", "prediction", "exercise", "theory", "message", "mode"}
    assert set(context["exercise"]) == {"title", "goal", "prompt", "params", "options"}
    assert "series" not in context["run"]
    assert "transfer" not in json.dumps(context, ensure_ascii=False)
    history = client.get(f"/api/sessions/{request['session_id']}/events").json()["events"]
    assert [row["stage"] for row in history] == ["predict", "run"]


def test_wrong_or_foreign_run_never_reaches_model(tutoring):
    client, model, request = tutoring
    assert client.post("/api/tutor/guide", json={**request, "run_id": str(uuid4())}).status_code == 404
    assert client.post("/api/tutor/guide", json={**request, "session_id": str(uuid4())}).status_code == 404
    assert model.contexts == []


@pytest.mark.parametrize("failure", ["foreign-evidence", "unknown-field", "non-json", "invalid-params", "empty-evidence"])
def test_model_cannot_return_invalid_evidence_or_parameters(tutoring, failure):
    client, model, request = tutoring
    if failure == "foreign-evidence":
        model.change["evidence"] = [{"run_id": str(uuid4()), "metric_key": "peak_frequency_hz"}]
    elif failure == "unknown-field":
        model.change["evidence"] = [{"run_id": request["run_id"], "metric_key": "invented"}]
    elif failure == "non-json":
        model.raw = "不是 JSON"
    elif failure == "invalid-params":
        model.change["next_experiment"] = {
            "experiment_type": "sampling_aliasing", "params": {"frequency_hz": 70, "sample_rate_hz": 0},
        }
    else:
        model.change["evidence"] = []
    response = client.post("/api/tutor/guide", json=request)
    assert response.status_code == 502
    assert response.json()["detail"] == "invalid_tutor_reply"


def test_timeout_leaves_the_experiment_available(tutoring, monkeypatch):
    from app.tutor import service

    client, model, request = tutoring
    monkeypatch.setattr(service, "TIMEOUT_SECONDS", 0.01)
    model.delay = 0.08
    response = client.post("/api/tutor/guide", json=request)
    assert response.status_code == 504
    assert response.json()["detail"] == "tutor_timeout"
    assert client.get("/api/experiments/" + request["run_id"]).status_code == 200


def test_confirmed_observation_preserves_the_formal_run_and_prediction(tutoring):
    client, model, request = tutoring
    session = request["session_id"]
    comparison = start_run(client, rate=200)
    assert event(client, str(uuid4()), "observe", run_id=comparison).status_code == 409
    assert event(client, session, "observe", run_id=comparison).status_code == 200
    response = client.post("/api/tutor/guide", json={**request, "run_id": comparison})
    assert response.status_code == 200
    assert response.json()["evidence"][0]["run_id"] == comparison
    assert model.contexts[-1]["prediction"]["value"] == 22
    assert model.contexts[-1]["exercise"]["params"]["sample_rate_hz"] == 110
    assert model.contexts[-1]["run"]["params"]["sample_rate_hz"] == 200
    answer = {"kind": "numeric", "value": 30.5, "unit": "Hz"}
    assert event(client, session, "transfer", run_id=comparison, answer=answer).status_code == 409
    assert event(client, session, "transfer", run_id=request["run_id"], answer=answer).json()["outcome"] == "correct"
    history = client.get(f"/api/sessions/{session}/events").json()["events"]
    assert [row["stage"] for row in history] == ["predict", "run", "observe", "transfer"]
    assert history[0]["answer"]["value"] == 22
    assert history[1]["run_id"] == request["run_id"]


def test_mode_b_wraps_plain_feedback_without_inventing_evidence(tutoring):
    client, model, request = tutoring
    model.raw = "比较当前观测主峰与原始频率，再考虑采样不足会怎样改变样本。"
    response = client.post("/api/tutor/guide", json={**request, "mode": "B"})
    assert response.status_code == 200
    assert response.json()["explanation"] == model.raw
    assert response.json()["evidence"] == []
    assert response.json()["next_experiment"] is None
    assert model.contexts[-1]["mode"] == "B"
