"""Dispatch the currently supported, validated experiment request."""

from app.experiments.sampling import build_sampling_run
from app.schemas import ExperimentRequest, ExperimentRun


def run_experiment(request: ExperimentRequest) -> ExperimentRun:
    return build_sampling_run(request.params)
