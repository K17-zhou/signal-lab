"""Run real storage, routes and engine with deterministic synthetic tutor replies."""

import csv
import json
import os
from pathlib import Path
import sys
from threading import Thread
from time import sleep
from uuid import uuid4

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app
from app.tutor.client import TutorTransportError


class SyntheticTutor:
    def __init__(self):
        with (ROOT / "evaluation" / "case_manifest.csv").open(encoding="utf-8", newline="") as source:
            row = next(row for row in csv.DictReader(source) if row["case_id"] == "I08")
        self.i08_v1 = json.loads(row["input"])
        with (ROOT / "evaluation" / "comparison-policy-v2.json").open(encoding="utf-8") as source:
            self.i08 = json.load(source)["I08"]
        self.i08_original_run = None

    def complete(self, context):
        run = context["run"]
        peak = run["metrics"]["peak_frequency_hz"]
        message = context["message"]
        if message == "验收模型离线":
            raise TutorTransportError("Synthetic offline model")
        if message == "I08 v1 旧版提议":
            return json.dumps({
                "focus": "sampling",
                "evidence": [{"run_id": run["run_id"], "metric_key": self.i08_v1["stub_evidence_metric"]}],
                "next_experiment": {"experiment_type": "sampling_aliasing", "params": self.i08_v1["comparison_params"]},
            })
        if message == "I08 原始对照":
            assert run["params"] == self.i08["formal_params"]
            self.i08_original_run = run["run_id"]
            return json.dumps({
                "focus": "sampling",
                "evidence": [{"run_id": run["run_id"], "metric_key": self.i08["stub_evidence_metric"]}],
                "next_experiment": {"experiment_type": "sampling_aliasing", "params": self.i08["comparison_params"]},
            })
        if message == "I08 引用旧运行":
            assert self.i08_original_run and run["params"] == self.i08["comparison_params"]
            return json.dumps({
                "focus": "sampling",
                "evidence": [{"run_id": self.i08_original_run, "metric_key": self.i08["stub_evidence_metric"]}],
                "next_experiment": None,
            })
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


def watch_stop_file(server: uvicorn.Server, stop_file: Path) -> None:
    while not stop_file.exists():
        sleep(0.1)
    server.should_exit = True


def main():
    stop_path = os.environ.get("SIGNAL_LAB_E2E_STOP_FILE")
    stop_file = Path(stop_path).resolve() if stop_path else None
    if stop_file and not stop_file.is_relative_to(ROOT):
        raise ValueError("Test fixture artifacts must stay in the project directory")
    qa = stop_file.parent / "fixture" if stop_file else ROOT / ".cache" / "qa" / "task7" / f"playwright-{uuid4().hex}"
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
    app = create_app(qa / "study.sqlite3", tutor_client=SyntheticTutor())
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18082, timeout_graceful_shutdown=3))
    if stop_file:
        Thread(target=watch_stop_file, args=(server, stop_file), daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
