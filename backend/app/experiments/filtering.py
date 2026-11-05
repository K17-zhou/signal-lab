"""Causal low-pass filtering of a fixed two-tone signal."""

from uuid import uuid4

import numpy as np
from scipy.fft import rfft, rfftfreq
from scipy.signal import butter, sosfilt

from app.schemas import FilteringMetrics, FilteringParams, FilteringRun, PlotSeries

SAMPLE_RATE_HZ = 1000
STEADY_START_S = 1
DURATION_S = 2
ENGINE_VERSION = "lowpass-butterworth-v1"


def _steady_spectrum(signal: np.ndarray) -> np.ndarray:
    steady = signal[STEADY_START_S * SAMPLE_RATE_HZ:]
    amplitude = np.abs(rfft(steady)) * (2 / steady.size)
    amplitude[[0, -1]] *= 0.5
    return amplitude


def build_filtering_run(params: FilteringParams) -> FilteringRun:
    time = np.arange(DURATION_S * SAMPLE_RATE_HZ, dtype=np.float64) / SAMPLE_RATE_HZ
    source = np.sin(2 * np.pi * 20 * time) + 0.5 * np.sin(2 * np.pi * 120 * time)
    sos = butter(4, params.cutoff_hz, btype="lowpass", fs=SAMPLE_RATE_HZ, output="sos")
    filtered = sosfilt(sos, source)
    source_spectrum = _steady_spectrum(source)
    filtered_spectrum = _steady_spectrum(filtered)
    frequency = rfftfreq((DURATION_S - STEADY_START_S) * SAMPLE_RATE_HZ, d=1 / SAMPLE_RATE_HZ)
    time_values, frequency_values = time.tolist(), frequency.tolist()
    unit = "relative amplitude"

    return FilteringRun(
        run_id=str(uuid4()),
        experiment_type="lowpass_filter",
        params=params,
        engine_version=ENGINE_VERSION,
        series=[
            PlotSeries(name="input", domain="time", x_unit="s", y_unit=unit, x=time_values, y=source.tolist()),
            PlotSeries(name="filtered", domain="time", x_unit="s", y_unit=unit, x=time_values, y=filtered.tolist()),
            PlotSeries(name="input_spectrum", domain="frequency", x_unit="Hz", y_unit=unit,
                       x=frequency_values, y=source_spectrum.tolist()),
            PlotSeries(name="filtered_spectrum", domain="frequency", x_unit="Hz", y_unit=unit,
                       x=frequency_values, y=filtered_spectrum.tolist()),
        ],
        # The one-second window gives 1 Hz bins at both component frequencies.
        metrics=FilteringMetrics(
            gain_20hz=float(filtered_spectrum[20] / source_spectrum[20]),
            gain_120hz=float(filtered_spectrum[120] / source_spectrum[120]),
            steady_state_start_s=STEADY_START_S,
            steady_state_end_s=DURATION_S,
        ),
        warnings=["FILTER_STARTUP_TRANSIENT", "CAUSAL_PHASE_SHIFT"],
    )
