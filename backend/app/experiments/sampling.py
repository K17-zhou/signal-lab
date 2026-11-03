"""One-second periodic sine sampling; never infer an unknown source signal."""

from uuid import uuid4

import numpy as np
from scipy.fft import rfft, rfftfreq
from scipy.signal import resample

from app.schemas import ExperimentRun, PlotSeries, SamplingMetrics, SamplingParams

REFERENCE_POINTS = 4096
ENGINE_VERSION = "sampling-periodic-v1"
DEGENERATE_RMS_THRESHOLD = 1e-8


def build_sampling_run(params: SamplingParams) -> ExperimentRun:
    """Compute all series and metrics from the same validated parameters."""
    frequency = params.frequency_hz
    sample_rate = params.sample_rate_hz
    reference_time = np.arange(REFERENCE_POINTS, dtype=np.float64) / REFERENCE_POINTS
    sample_time = np.arange(sample_rate, dtype=np.float64) / sample_rate

    reference = params.amplitude * np.sin(
        2 * np.pi * frequency * reference_time + params.phase_rad
    )
    # Direct analytical sampling preserves aliasing; downsampling through an
    # antialiasing helper would remove the phenomenon we are teaching.
    samples = params.amplitude * np.sin(
        2 * np.pi * frequency * sample_time + params.phase_rad
    )
    rebuilt = resample(samples, REFERENCE_POINTS)

    amplitude_spectrum = np.abs(rfft(samples)) * (2 / sample_rate)
    amplitude_spectrum[0] /= 2
    if sample_rate % 2 == 0:
        amplitude_spectrum[-1] /= 2
    frequency_axis = rfftfreq(sample_rate, d=1 / sample_rate)

    sample_rms = float(np.sqrt(np.mean(samples**2)))
    alias_frequency = abs(((frequency + sample_rate / 2) % sample_rate) - sample_rate / 2)
    warnings = ["PERIODIC_SIGNAL_MODEL"]
    if sample_rate == 2 * frequency:
        sampling_state = "nyquist_boundary"
        warnings.append("NYQUIST_BOUNDARY")
    elif sample_rate < 2 * frequency:
        sampling_state = "undersampled"
        warnings.append("UNDERSAMPLED")
    else:
        sampling_state = "well_sampled"

    if sample_rms < DEGENERATE_RMS_THRESHOLD:
        peak_frequency = None
        warnings.append("DEGENERATE_SAMPLES")
    else:
        peak_frequency = float(frequency_axis[int(np.argmax(amplitude_spectrum))])

    def time_series(name: str, times: np.ndarray, values: np.ndarray) -> PlotSeries:
        return PlotSeries(
            name=name, domain="time", x_unit="s", y_unit="relative amplitude",
            x=times.tolist(), y=values.tolist(),
        )

    return ExperimentRun(
        run_id=str(uuid4()),
        experiment_type="sampling_aliasing",
        params=params,
        engine_version=ENGINE_VERSION,
        series=[
            time_series("reference", reference_time, reference),
            time_series("samples", sample_time, samples),
            time_series("reconstruction", reference_time, rebuilt),
            PlotSeries(
                name="spectrum", domain="frequency", x_unit="Hz",
                y_unit="relative amplitude", x=frequency_axis.tolist(),
                y=amplitude_spectrum.tolist(),
            ),
        ],
        metrics=SamplingMetrics(
            alias_frequency_hz=float(alias_frequency),
            sampling_state=sampling_state,
            sample_rms=sample_rms,
            peak_frequency_hz=peak_frequency,
            reconstruction_rmse=float(np.sqrt(np.mean((rebuilt - reference) ** 2))),
        ),
        warnings=warnings,
    )
