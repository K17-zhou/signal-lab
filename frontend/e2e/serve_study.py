"""Run real storage, routes and engine with deterministic synthetic tutor replies."""

import csv
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app


class SyntheticTutor:
    def complete(self, context):
        run = context["run"]
        peak = run["metrics"]["peak_frequency_hz"]
        if context["mode"] == "B":
            if run["params"]["frequency_hz"] == 38:
                raise TimeoutError
            return f"请核对记录中的 {peak:g} Hz 主峰和原始频率。"
        return json.dumps({
            "focus": "sampling",
            "evidence": [{"run_id": run["run_id"], "metric_key": "peak_frequency_hz"}],
            "next_experiment": {
                "experiment_type": "sampling_aliasing",
                "params": {**run["params"], "sample_rate_hz": 400},
            },
        })


def main():
    qa = ROOT / ".cache" / "qa" / "task6" / f"playwright-{uuid4().hex}"
    qa.mkdir(parents=True)
    assignments = qa / "synthetic-assignments.csv"
    with assignments.open("x", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(("participant_id", "session_id", "condition", "form", "order_index", "cohort", "model_config"))
        for index, (participant, condition, form, order) in enumerate(
            (("P91", "B", "X", 1), ("P91", "C", "Y", 2),
             ("P92", "B", "Y", 1), ("P92", "C", "X", 2)),
            start=1,
        ):
            writer.writerow((participant, f"00000000-0000-4000-8000-{index:012d}",
                             condition, form, order, "pilot", "synthetic-playwright-fixture"))
    os.environ["SIGNAL_LAB_STUDY_ASSIGNMENTS"] = str(assignments)
    uvicorn.run(create_app(qa / "study.sqlite3", tutor_client=SyntheticTutor()), host="127.0.0.1", port=18082)


if __name__ == "__main__":
    main()
