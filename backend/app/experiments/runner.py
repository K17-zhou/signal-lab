"""Dispatch the currently supported, validated experiment request."""

from app.experiments.filtering import build_filtering_run
from app.experiments.sampling import build_sampling_run
from app.schemas import ExperimentInput, ExperimentResult


def run_experiment(request: ExperimentInput) -> ExperimentResult:
    if request.experiment_type == "lowpass_filter":
        return build_filtering_run(request.params)
    return build_sampling_run(request.params)
