"""Check the saved low-pass experiment against independent Butterworth references."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def payload(cutoff):
    return {"experiment_type": "lowpass_filter", "params": {"cutoff_hz": cutoff}}


def test_causal_lowpass_measures_gain_from_the_final_second(tmp_path):
    database = tmp_path / "lab.sqlite3"
    with TestClient(create_app(database)) as client:
        response = client.post("/api/experiments/run", json=payload(60))
        assert response.status_code == 200, response.text
        run = response.json()
    metrics = run["metrics"]
    # Closed-form digital Butterworth magnitudes, independent of the SOS output.
    assert metrics["gain_20hz"] == pytest.approx(0.99993001, abs=0.005)
    assert metrics["gain_120hz"] == pytest.approx(0.05380920, abs=0.005)
    assert (metrics["steady_state_start_s"], metrics["steady_state_end_s"]) == (1, 2)
    series = {item["name"]: item for item in run["series"]}
    assert len(series["input"]["x"]) == len(series["filtered"]["x"]) == 2000
    assert series["filtered"]["y"][0] == 0
    assert series["filtered"]["y"][1] != pytest.approx(series["input"]["y"][1])
    assert series["input_spectrum"]["y"][120] == pytest.approx(0.5)
    assert series["filtered_spectrum"]["y"][120] / 0.5 == pytest.approx(metrics["gain_120hz"])
    with TestClient(create_app(database)) as client:
        assert client.get(f"/api/experiments/{run['run_id']}").json() == run


@pytest.mark.parametrize("cutoff", [30, 90.5, 200])
def test_cutoff_range_includes_endpoints_and_fractional_values(tmp_path, cutoff):
    with TestClient(create_app(tmp_path / "lab.sqlite3")) as client:
        response = client.post("/api/experiments/run", json=payload(cutoff))
        assert response.status_code == 200, response.text
        assert response.json()["params"]["cutoff_hz"] == cutoff


@pytest.mark.parametrize("cutoff", [0, 29, 201, 500, True, "60"])
def test_invalid_cutoff_is_rejected(tmp_path, cutoff):
    with TestClient(create_app(tmp_path / "lab.sqlite3")) as client:
        assert client.post("/api/experiments/run", json=payload(cutoff)).status_code == 422
