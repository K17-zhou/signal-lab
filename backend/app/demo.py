"""Export real runs of the four design fixtures for manual inspection."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from app.experiments.runner import run_experiment
from app.schemas import ExperimentRequest


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the four sampling fixtures.")
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    args = parser.parse_args()
    try:
        args.output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error(f"output directory already exists: {args.output}")

    cases = []
    for case_id, frequency, sample_rate in [
        ("S1", 50, 400), ("S2", 70, 100),
        ("S3", 50, 100), ("S4", 100, 100),
    ]:
        run = run_experiment(ExperimentRequest(
            experiment_type="sampling_aliasing",
            params={"frequency_hz": frequency, "sample_rate_hz": sample_rate},
        ))
        (args.output / f"{case_id}.json").write_text(
            run.model_dump_json(), encoding="utf-8"
        )
        cases.append({
            "case_id": case_id,
            "run_id": run.run_id,
            "params": run.params.model_dump(),
            "metrics": run.metrics.model_dump(),
            "warnings": run.warnings,
            "result_file": f"{case_id}.json",
        })

    summary = {
        "source": "synthetic_periodic_model",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "engine_version": run.engine_version,
        "cases": cases,
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, allow_nan=False, indent=2),
        encoding="utf-8",
    )
    print(f"Exported {len(cases)} computed runs to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
