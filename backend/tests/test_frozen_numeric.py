"""Run the frozen Task 7 numeric holdouts through the public experiments API."""

from contextlib import closing
import csv
import json
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
import numpy as np
import pytest

from app.main import create_app


MANIFEST = Path(__file__).resolve().parents[2] / "evaluation" / "case_manifest.csv"
FREQUENCY_TOLERANCE = 1e-9
AMPLITUDE_TOLERANCE = 1e-10
RECONSTRUCTION_FORMULAS = {
    "1.4 sin(2π·25t+0.6)": lambda t: 1.4 * np.sin(2 * np.pi * 25 * t + 0.6),
    "-0.4": lambda t: np.full_like(t, -0.4),
}


@pytest.fixture(scope="module")
def numeric_holdouts():
    with MANIFEST.open(encoding="utf-8", newline="") as manifest:
        return {
            row["case_id"]: row
            for row in csv.DictReader(manifest)
            if row["category"] == "numeric_boundary" and row["holdout"] == "true"
        }


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.delenv("SIGNAL_LAB_STUDY_ASSIGNMENTS", raising=False)
    monkeypatch.setenv("SIGNAL_LAB_TUTOR_MODEL", "")
    database = tmp_path / "frozen-numeric.sqlite3"
    with TestClient(create_app(database_path=database)) as client:
        yield client, database


def post_frozen_case(client, case):
    expected = json.loads(case["expected"])
    method, path = case["target"].split(" ", 1)
    response = client.request(
        method, path, content=case["input"], headers={"Content-Type": "application/json"}
    )
    assert response.status_code == expected["status"], response.text[:400]
    return response.json(), expected


@pytest.mark.parametrize("case_id", ["N04", "N06", "N10", "N12", "N14"])
def test_frozen_sampling(case_id, numeric_holdouts, lab):
    client, _ = lab
    run, expected = post_frozen_case(client, numeric_holdouts[case_id])
    metrics = run["metrics"]
    print(f"{case_id} metrics={metrics} warnings={run['warnings']}")
    assert set(run["warnings"]) == set(expected["warnings"])
    for name, value in expected["metrics"].items():
        if isinstance(value, (int, float)):
            tolerance = (
                FREQUENCY_TOLERANCE if name.endswith("_hz") else AMPLITUDE_TOLERANCE
            )
            assert metrics[name] == pytest.approx(value, rel=0, abs=tolerance), name
        else:
            assert metrics[name] == value, name

    series = {item["name"]: item for item in run["series"]}
    spectrum = series["spectrum"]
    line = expected["spectrum_line"]
    frequency, amplitude = min(
        zip(spectrum["x"], spectrum["y"], strict=True),
        key=lambda point: abs(point[0] - line["frequency_hz"]),
    )
    print(f"{case_id} spectrum_frequency_hz={frequency} spectrum_amplitude={amplitude}")
    assert frequency == pytest.approx(line["frequency_hz"], rel=0, abs=FREQUENCY_TOLERANCE)
    assert amplitude == pytest.approx(line["amplitude"], rel=0, abs=AMPLITUDE_TOLERANCE)

    samples = series["samples"]
    if "sample_count" in expected:
        print(f"{case_id} sample_count={len(samples['y'])} last_time_s={samples['x'][-1]}")
        assert len(samples["x"]) == len(samples["y"]) == expected["sample_count"]
        assert samples["x"][-1] == pytest.approx(expected["sample_last_time_s"], rel=0, abs=1e-12)
    if "sample_prefix" in expected:
        prefix = samples["y"][:len(expected["sample_prefix"])]
        print(f"{case_id} sample_prefix={prefix}")
        assert prefix == pytest.approx(expected["sample_prefix"], rel=0, abs=AMPLITUDE_TOLERANCE)
    if case_id == "N14":
        assert metrics["sample_rms"] > 1e-8
    if "reconstruction_formula" in expected:
        rebuilt = series["reconstruction"]
        assert len(rebuilt["x"]) == len(rebuilt["y"]) > 0
        formula = RECONSTRUCTION_FORMULAS[expected["reconstruction_formula"]]
        values = formula(np.asarray(rebuilt["x"]))
        error = np.max(np.abs(np.asarray(rebuilt["y"]) - values))
        print(f"{case_id} reconstruction_points={len(values)} max_absolute_error={error}")
        np.testing.assert_allclose(
            rebuilt["y"], values, rtol=0, atol=AMPLITUDE_TOLERANCE, equal_nan=False
        )


def test_n16_frozen_fractional_sample_rate(numeric_holdouts, lab):
    client, database = lab
    with closing(sqlite3.connect(database)) as connection:
        (before,) = connection.execute("SELECT COUNT(*) FROM runs").fetchone()
        body, expected = post_frozen_case(client, numeric_holdouts["N16"])
        (after,) = connection.execute("SELECT COUNT(*) FROM runs").fetchone()

    print(f"N16 error={body} runs_before={before} runs_after={after}")
    assert "run_id" not in body
    errors = [(item["loc"][-2:], item["type"]) for item in body["detail"]]
    assert errors == [(["params", expected["error_field"]], expected["error_type"])]
    assert (after != before) == expected["run_created"], f"runs before={before}, after={after}"


def test_n19_frozen_filter_cutoff(numeric_holdouts, lab):
    client, _ = lab
    run, expected = post_frozen_case(client, numeric_holdouts["N19"])
    metrics = run["metrics"]
    print(f"N19 metrics={metrics} warnings={run['warnings']}")
    assert set(run["warnings"]) == set(expected["warnings"])
    for name, value in expected["metrics"].items():
        if name.startswith("gain_"):
            assert abs(metrics[name] - value) < 0.005, f"{name}: expected {value}, got {metrics[name]}"
        else:
            assert metrics[name] == value, name
