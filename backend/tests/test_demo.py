"""Exercise the actual command-line entry point, without a mock engine."""

import json
from pathlib import Path
import subprocess
import sys


BACKEND = Path(__file__).resolve().parents[1]


def test_demo_exports_computed_cases(tmp_path):
    """Catches exporting canned summaries instead of actual experiment runs."""
    target = tmp_path / "examples"
    result = subprocess.run(
        [sys.executable, "-m", "app.demo", "--output", str(target)],
        cwd=BACKEND, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads((target / "summary.json").read_text(encoding="utf-8"))
    assert summary["source"] == "synthetic_periodic_model"
    assert len(summary["cases"]) == 4
    by_case = {case["case_id"]: case for case in summary["cases"]}
    assert by_case["S1"]["metrics"]["alias_frequency_hz"] == 50
    assert by_case["S2"]["metrics"]["alias_frequency_hz"] == 30
    assert by_case["S3"]["metrics"]["peak_frequency_hz"] is None
    full_run = json.loads((target / "S2.json").read_text(encoding="utf-8"))
    assert full_run["run_id"] == by_case["S2"]["run_id"]
    assert next(item for item in full_run["series"] if item["name"] == "samples")["y"][1] < -0.9


def test_demo_does_not_overwrite_an_existing_result_directory(tmp_path):
    """Catches losing existing evidence when rerunning the export command."""
    target = tmp_path / "existing"
    target.mkdir()
    receipt = target / "summary.json"
    receipt.write_text("keep existing evidence", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "app.demo", "--output", str(target)],
        cwd=BACKEND, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0
    assert "already exists" in result.stderr.casefold()
    assert receipt.read_text(encoding="utf-8") == "keep existing evidence"
    assert not (target / "S1.json").exists()
