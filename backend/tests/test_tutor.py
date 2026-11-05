"""AI explanations may cite only data from the saved run."""

import json
import time
from unittest.mock import Mock
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.tutor.client import TutorClient


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
            "focus": "sampling",
            "evidence": [{"run_id": context["run"]["run_id"], "metric_key": "peak_frequency_hz"}],
            "next_experiment": {
                "experiment_type": "sampling_aliasing",
                "params": {"frequency_hz": 70, "sample_rate_hz": 200},
            },
            **self.change,
        })


def start_run(client, frequency=70, rate=110, **params):
    result = client.post("/api/experiments/run", json={
        "experiment_type": "sampling_aliasing",
        "params": {"frequency_hz": frequency, "sample_rate_hz": rate, **params},
    })
    assert result.status_code == 200
    return result.json()["run_id"]


def event(client, session_id, stage, case_id="alias-frequency", **fields):
    return client.post("/api/events", json={
        "event_id": str(uuid4()), "session_id": session_id,
        "case_id": case_id, "stage": stage, "elapsed_ms": 10,
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
    assert "你的原预测是 22 Hz" in result["explanation"]
    assert "理论折叠频率为 40 Hz" in result["explanation"]
    assert "观测主峰为 40 Hz" in result["explanation"]
    assert result["evidence"] == [{"run_id": request["run_id"], "metric_key": "peak_frequency_hz"}]
    assert result["next_experiment"]["params"]["sample_rate_hz"] == 200
    context = model.contexts[0]
    assert context["prediction"] == {"kind": "numeric", "value": 22.0, "unit": "Hz"}
    assert context["run"]["metrics"]["peak_frequency_hz"] == pytest.approx(40)
    assert set(context) == {"run", "prediction", "exercise", "theory", "message", "mode"}
    assert "本次运行属于欠采样" in context["theory"]
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


@pytest.mark.parametrize("failure", [
    "foreign-evidence", "unknown-field", "non-json", "invalid-params", "empty-evidence",
    "unverified-explanation", "unknown-focus",
])
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
    elif failure == "empty-evidence":
        model.change["evidence"] = []
    elif failure == "unverified-explanation":
        model.change["explanation"] = "理论折叠频率为 999 Hz。"
    else:
        model.change["focus"] = "invented"
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
    explanation = response.json()["explanation"]
    assert "原题采样率为 110 Hz" in explanation
    assert "你的原预测是 22 Hz" in explanation
    assert "本次采样率为 200 Hz" in explanation
    assert "观测主峰为 70 Hz" in explanation
    assert model.contexts[-1]["prediction"]["value"] == 22
    assert model.contexts[-1]["exercise"]["params"]["sample_rate_hz"] == 110
    assert model.contexts[-1]["run"]["params"]["sample_rate_hz"] == 200
    assert "本次运行满足充分采样条件" in model.contexts[-1]["theory"]
    answer = {"kind": "numeric", "value": 30.5, "unit": "Hz"}
    assert event(client, session, "transfer", run_id=comparison, answer=answer).status_code == 409
    assert event(client, session, "transfer", run_id=request["run_id"], answer=answer).json()["outcome"] == "correct"
    history = client.get(f"/api/sessions/{session}/events").json()["events"]
    assert [row["stage"] for row in history] == ["predict", "run", "observe", "transfer"]
    assert history[0]["answer"]["value"] == 22
    assert history[1]["run_id"] == request["run_id"]


@pytest.mark.parametrize(("phase", "observed"), [
    (0.0, "未检测到可辨主峰"),
    (1.5707963267948966, "观测主峰为 50 Hz"),
])
def test_nyquist_boundary_separates_folded_frequency_from_observed_peak(tutoring, phase, observed):
    client, _, request = tutoring
    run_id = start_run(client, frequency=50, rate=100, phase_rad=phase)
    assert event(client, request["session_id"], "observe", run_id=run_id).status_code == 200

    response = client.post("/api/tutor/guide", json={**request, "run_id": run_id})

    assert response.status_code == 200
    explanation = response.json()["explanation"]
    assert "理论折叠频率为 50 Hz" in explanation
    assert observed in explanation
    assert "无法保证唯一恢复" in explanation


@pytest.mark.parametrize(("case_id", "frequency", "rate", "option", "expected"), [
    ("smoothness", 90, 125, "enough", "光滑且经过样本不足以证明恢复"),
    ("post-filter", 95, 140, "recover", "采样后低通无法按原始来源分离"),
])
def test_generic_focus_keeps_the_exercises_specific_guidance(tutoring, case_id, frequency, rate, option, expected):
    client, _, _ = tutoring
    session = str(uuid4())
    answer = {"kind": "choice", "option_id": option}
    assert event(client, session, "predict", case_id, answer=answer).status_code == 200
    run_id = start_run(client, frequency=frequency, rate=rate)
    assert event(client, session, "run", case_id, run_id=run_id).status_code == 200

    response = client.post("/api/tutor/guide", json={
        "session_id": session, "run_id": run_id, "message": "解释这道题的现象。",
    })

    assert response.status_code == 200
    assert expected in response.json()["explanation"]


def test_mode_b_wraps_plain_feedback_without_inventing_evidence(tutoring):
    client, model, request = tutoring
    model.raw = "比较当前观测主峰与原始频率，再考虑采样不足会怎样改变样本。"
    response = client.post("/api/tutor/guide", json={**request, "mode": "B"})
    assert response.status_code == 200
    assert response.json()["explanation"] == model.raw
    assert response.json()["evidence"] == []
    assert response.json()["next_experiment"] is None
    assert model.contexts[-1]["mode"] == "B"


def test_structured_client_sends_schema_in_llama_cpp_envelope(monkeypatch):
    connection = Mock()
    response = connection.getresponse.return_value
    response.status = 200
    response.read.return_value = b'{"choices":[{"message":{"content":"{}"}}]}'
    monkeypatch.setattr("app.tutor.client.HTTPConnection", Mock(return_value=connection))
    run_id = str(uuid4())

    TutorClient("signal-lab-tutor").complete({"mode": "C", "run": {"run_id": run_id}})

    payload = json.loads(connection.request.call_args.args[2])
    assert payload["response_format"]["type"] == "json_schema"
    schema = payload["response_format"]["json_schema"]["schema"]
    assert schema["$defs"]["EvidenceRef"]["properties"]["run_id"] == {"const": run_id}
    assert schema["properties"]["evidence"]["minItems"] == 1
    assert "explanation" not in schema["properties"]
    assert "phase" in schema["properties"]["focus"]["enum"]
