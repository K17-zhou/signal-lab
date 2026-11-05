"""Exercise persisted real runs and invalid JSON/physical input boundaries."""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path


def make_app(database_path):
    from app.main import create_app
    return create_app(database_path=database_path)


def sampling_payload(**changes):
    return {
        "experiment_type": "sampling_aliasing",
        "params": {"frequency_hz": 70, "sample_rate_hz": 100, **changes},
    }


def test_default_database_stays_in_the_project(monkeypatch):
    import app.main as main

    created_paths = []
    monkeypatch.delenv("SIGNAL_LAB_DB_PATH", raising=False)
    monkeypatch.setattr(main, "Store", lambda path: created_paths.append(Path(path)))
    with TestClient(main.create_app()) as client:
        assert client.get("/api/health").status_code == 200
    project = Path(__file__).resolve().parents[2]
    assert created_paths == [project / ".cache" / "signal-lab.sqlite3"]


def test_run_returns_real_metrics_and_can_be_retrieved(tmp_path):
    with TestClient(make_app(tmp_path / "lab.sqlite3")) as client:
        response = client.post("/api/experiments/run", json=sampling_payload())
        assert response.status_code == 200
        run = response.json()
        assert run["metrics"]["alias_frequency_hz"] == 30
        assert run["metrics"]["sampling_state"] == "undersampled"
        assert next(s for s in run["series"] if s["name"] == "samples")["y"][1] < -0.9
        retrieved = client.get(f"/api/experiments/{run['run_id']}")
        assert retrieved.status_code == 200
        assert retrieved.json() == run


def test_run_persists_after_application_restart(tmp_path):
    database = tmp_path / "lab.sqlite3"
    with TestClient(make_app(database)) as client:
        saved = client.post("/api/experiments/run", json=sampling_payload()).json()
    with TestClient(make_app(database)) as client:
        assert client.get(f"/api/experiments/{saved['run_id']}").json() == saved


@pytest.mark.parametrize("params", [{"frequency_hz": 201}, {"sample_rate_hz": 0}, {"frequency_hz": "70"}, {"amplitude": 0}])
def test_invalid_physical_requests_return_422(tmp_path, params):
    with TestClient(make_app(tmp_path / "lab.sqlite3")) as client:
        assert client.post("/api/experiments/run", json=sampling_payload(**params)).status_code == 422


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_returns_a_serializable_422_not_a_server_error(tmp_path, token):
    body = '{"experiment_type":"sampling_aliasing","params":{"frequency_hz":70,"sample_rate_hz":100,"amplitude":' + token + '}}'
    with TestClient(make_app(tmp_path / "lab.sqlite3")) as client:
        response = client.post("/api/experiments/run", content=body, headers={"Content-Type": "application/json"})
        assert response.status_code == 422
        assert response.json()["detail"]
        assert token not in response.text


def test_unknown_experiment_and_run_are_explicit(tmp_path):
    with TestClient(make_app(tmp_path / "lab.sqlite3")) as client:
        response = client.post("/api/experiments/run", json={"experiment_type": "unknown", "params": {"cutoff_hz": 60}})
        assert response.status_code == 422
        assert client.get("/api/experiments/not-a-run").status_code == 404


def test_store_preserves_existing_run_when_identifier_is_reused(tmp_path):
    from app.experiments.runner import run_experiment
    from app.schemas import ExperimentRequest
    from app.store import Store

    store = Store(tmp_path / "lab.sqlite3")
    first = run_experiment(ExperimentRequest(**sampling_payload()))
    store.put_run(first)
    other = run_experiment(ExperimentRequest(**sampling_payload(frequency_hz=50)))
    conflicting = other.model_copy(update={"run_id": first.run_id})
    with pytest.raises(ValueError):
        store.put_run(conflicting)
    assert store.get_run(first.run_id) == first
