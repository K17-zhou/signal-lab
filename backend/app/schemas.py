"""Validated data contracts for the sampling experiment."""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FrozenRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class SamplingParams(FrozenRecord):
    frequency_hz: int = Field(strict=True, ge=5, le=200)
    sample_rate_hz: int = Field(strict=True, ge=20, le=1000)
    amplitude: float = Field(default=1.0, strict=True, ge=0.1, le=2.0)
    phase_rad: float = Field(default=0.0, strict=True, ge=-math.pi, le=math.pi)


class ExperimentRequest(FrozenRecord):
    # Filtering is deliberately not enabled before the optional P1 task.
    experiment_type: Literal["sampling_aliasing"]
    params: SamplingParams


class PlotSeries(FrozenRecord):
    name: str
    domain: Literal["time", "frequency"]
    x_unit: str
    y_unit: str
    x: list[float]
    y: list[float]


class SamplingMetrics(FrozenRecord):
    alias_frequency_hz: float
    sampling_state: Literal["well_sampled", "undersampled", "nyquist_boundary"]
    sample_rms: float
    peak_frequency_hz: float | None
    reconstruction_rmse: float


class ExperimentRun(FrozenRecord):
    run_id: str
    experiment_type: Literal["sampling_aliasing"]
    params: SamplingParams
    engine_version: str
    series: list[PlotSeries]
    metrics: SamplingMetrics
    warnings: list[str]
