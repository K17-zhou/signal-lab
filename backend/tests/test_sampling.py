"""Physics fixtures are hand-derived, independent of the implementation."""

import json
import math

import numpy as np
import pytest


def run_sampling(frequency_hz=50, sample_rate_hz=400, **params):
    # Import here so a missing implementation is an individual RED test failure.
    from app.experiments.runner import run_experiment
    from app.schemas import ExperimentRequest

    request = ExperimentRequest(
        experiment_type="sampling_aliasing",
        params={
            "frequency_hz": frequency_hz,
            "sample_rate_hz": sample_rate_hz,
            **params,
        },
    )
    return run_experiment(request)


def series(run, name):
    return next(item for item in run.series if item.name == name)


def test_safe_sampling_reconstructs():
    """Catches frequency-axis, amplitude, or reconstruction scaling errors."""
    run = run_sampling()
    assert run.metrics.alias_frequency_hz == 50
    assert run.metrics.sampling_state == "well_sampled"
    assert run.metrics.peak_frequency_hz == 50
    assert run.metrics.reconstruction_rmse < 1e-10
    samples = series(run, "samples")
    np.testing.assert_allclose(
        samples.y[:4], [0, math.sqrt(0.5), 1, math.sqrt(0.5)], atol=1e-12
    )
    assert "PERIODIC_SIGNAL_MODEL" in run.warnings


def test_aliases_70hz_to_negative_30hz():
    """Catches hidden anti-aliasing, folding-sign or false-recovery errors."""
    run = run_sampling(70, 100)
    assert run.metrics.alias_frequency_hz == 30
    assert run.metrics.peak_frequency_hz == 30
    assert run.metrics.sampling_state == "undersampled"
    rebuilt = series(run, "reconstruction")
    expected = -np.sin(2 * np.pi * 30 * np.array(rebuilt.x))
    np.testing.assert_allclose(rebuilt.y, expected, atol=1e-10)
    assert run.metrics.reconstruction_rmse == pytest.approx(1, abs=1e-10)
    assert "UNDERSAMPLED" in run.warnings


def test_nyquist_zero_samples():
    """Catches interpreting floating noise as a recovered Nyquist signal."""
    run = run_sampling(50, 100)
    assert run.metrics.sampling_state == "nyquist_boundary"
    assert run.metrics.sample_rms < 1e-8
    assert run.metrics.peak_frequency_hz is None
    assert "NYQUIST_BOUNDARY" in run.warnings
    assert "DEGENERATE_SAMPLES" in run.warnings
    assert run.metrics.reconstruction_rmse > 0.7


def test_integer_multiple_of_sample_rate_is_not_nyquist_boundary():
    """Catches conflating DC folding with the Nyquist boundary."""
    run = run_sampling(100, 100)
    assert run.metrics.alias_frequency_hz == 0
    assert run.metrics.sampling_state == "undersampled"
    assert run.metrics.peak_frequency_hz is None
    assert "DEGENERATE_SAMPLES" in run.warnings
    assert "NYQUIST_BOUNDARY" not in run.warnings


def test_nonzero_dc_alias_is_not_doubled_or_suppressed():
    """Catches DC amplitude doubling or treating all DC as zero."""
    run = run_sampling(100, 100, phase_rad=math.pi / 2)
    spectrum = series(run, "spectrum")
    assert spectrum.x[0] == 0
    assert spectrum.y[0] == pytest.approx(1, abs=1e-12)
    assert run.metrics.peak_frequency_hz == 0
    assert "DEGENERATE_SAMPLES" not in run.warnings
    np.testing.assert_allclose(series(run, "reconstruction").y, 1, atol=1e-10)


def test_nyquist_bin_keeps_unit_amplitude():
    """Catches doubling the even-length Nyquist bin."""
    run = run_sampling(50, 100, phase_rad=math.pi / 2)
    spectrum = series(run, "spectrum")
    assert spectrum.x[-1] == 50
    assert spectrum.y[-1] == pytest.approx(1, abs=1e-12)
    assert run.metrics.peak_frequency_hz == 50
    assert run.metrics.sampling_state == "nyquist_boundary"


def test_odd_length_final_bin_is_a_regular_positive_frequency():
    """Catches halving the last FFT bin when the sample count is odd."""
    run = run_sampling(50, 101)
    spectrum = series(run, "spectrum")
    assert spectrum.x[-1] == pytest.approx(50)
    assert spectrum.y[-1] == pytest.approx(1, abs=1e-12)
    assert run.metrics.sampling_state == "well_sampled"
    assert run.metrics.reconstruction_rmse < 1e-10


def test_amplitude_and_phase_are_preserved():
    """Catches discarding amplitude or phase from a user request."""
    run = run_sampling(25, 400, amplitude=2, phase_rad=math.pi / 2)
    assert series(run, "samples").y[0] == pytest.approx(2)
    spectrum = series(run, "spectrum")
    assert spectrum.y[25] == pytest.approx(2)
    assert run.metrics.sample_rms == pytest.approx(math.sqrt(2))
    assert run.metrics.reconstruction_rmse < 1e-10


def test_sampling_grid_excludes_the_duplicate_period_endpoint():
    """Catches linspace(endpoint=True), which changes the sample rate."""
    run = run_sampling()
    samples = series(run, "samples")
    assert len(samples.x) == 400
    assert samples.x[1] == pytest.approx(1 / 400)
    assert samples.x[-1] == pytest.approx(399 / 400)
    assert samples.x_unit == "s"
    assert series(run, "spectrum").x_unit == "Hz"


@pytest.mark.parametrize("frequency,sample_rate,expected", [(170, 100, 30), (190, 80, 30), (200, 20, 0)])
def test_multiple_folds_have_the_correct_observed_frequency(frequency, sample_rate, expected):
    """Catches using only the first folding branch for high frequencies."""
    assert run_sampling(frequency, sample_rate).metrics.alias_frequency_hz == expected


def test_result_is_finite_json_and_has_a_unique_run_id():
    """Catches non-JSON numpy data, nonfinite metrics, or reused run IDs."""
    first = run_sampling()
    second = run_sampling()
    decoded = json.loads(json.dumps(first.model_dump(), allow_nan=False))
    assert decoded["experiment_type"] == "sampling_aliasing"
    assert decoded["params"]["frequency_hz"] == 50
    assert first.run_id != second.run_id
    assert first.metrics == second.metrics
    assert first.series == second.series


@pytest.mark.parametrize(
    "field,value",
    [
        ("frequency_hz", 4), ("frequency_hz", 201),
        ("frequency_hz", 5.5), ("frequency_hz", True),
        ("frequency_hz", "50"),
        ("sample_rate_hz", 19), ("sample_rate_hz", 1001),
        ("sample_rate_hz", 100.5),
        ("amplitude", 0), ("amplitude", 2.1),
        ("amplitude", float("nan")), ("amplitude", float("inf")),
        ("phase_rad", math.pi + 0.01), ("phase_rad", float("nan")),
    ],
)
def test_invalid_parameters_are_rejected_before_computation(field, value):
    """Catches silently coercing invalid physical inputs into a valid run."""
    from pydantic import ValidationError
    from app.schemas import ExperimentRequest

    params = {"frequency_hz": 50, "sample_rate_hz": 400, field: value}
    with pytest.raises(ValidationError):
        ExperimentRequest(experiment_type="sampling_aliasing", params=params)


def test_unknown_fields_and_experiments_are_not_silently_accepted():
    """Catches ignoring misspelled parameters or unsupported experiment types."""
    from pydantic import ValidationError
    from app.schemas import ExperimentRequest

    with pytest.raises(ValidationError):
        ExperimentRequest(experiment_type="arbitrary_code", params={"frequency_hz": 50, "sample_rate_hz": 400})
    with pytest.raises(ValidationError):
        ExperimentRequest(experiment_type="sampling_aliasing", params={"frequency_hz": 50, "sample_rate_hz": 400, "fake_gain": 2})
