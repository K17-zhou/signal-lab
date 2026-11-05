"""Validated data contracts for experiments and learning records."""

from datetime import datetime
import math
from typing import Annotated, Literal, Self

from pydantic import UUID4, BaseModel, ConfigDict, Field, StringConstraints, model_validator


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


class ChoiceAnswer(FrozenRecord):
    kind: Literal["choice"]
    option_id: str = Field(min_length=1, max_length=64)


class NumericAnswer(FrozenRecord):
    kind: Literal["numeric"]
    value: float = Field(strict=True)
    unit: Literal["Hz"]


AssessmentAnswer = Annotated[ChoiceAnswer | NumericAnswer, Field(discriminator="kind")]
LearningStage = Literal["predict", "run", "observe", "reflect", "transfer", "export", "error"]
LearningOutcome = Literal["recorded", "completed", "correct", "incorrect", "failed"]


class ScoreResult(FrozenRecord):
    correct: bool
    misconception_code: str | None
    explanation_key: str


class LearningEventRequest(FrozenRecord):
    event_id: UUID4
    session_id: UUID4
    case_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9-]+$")
    stage: LearningStage
    run_id: UUID4 | None = None
    answer: AssessmentAnswer | None = None
    note: str | None = Field(default=None, max_length=2000)
    elapsed_ms: int = Field(strict=True, ge=0)

    @model_validator(mode="after")
    def check_stage_fields(self) -> Self:
        if (self.stage in ("predict", "transfer")) != (self.answer is not None):
            raise ValueError("Only prediction and transfer events require an answer")
        if self.stage in ("run", "observe", "reflect", "transfer") and self.run_id is None:
            raise ValueError("This stage requires a saved run")
        if self.stage == "predict" and self.run_id is not None:
            raise ValueError("A prediction must precede the experiment")
        if self.note is not None and self.stage not in ("reflect", "error"):
            raise ValueError("Only reflection and error events accept a note")
        if self.stage == "reflect" and not (self.note or "").strip():
            raise ValueError("A reflection requires a nonempty note")
        return self


class LearningEvent(LearningEventRequest):
    outcome: LearningOutcome
    timestamp: datetime


class SessionHistory(FrozenRecord):
    session_id: UUID4
    events: list[LearningEvent]


EvidenceKey = Literal[
    "frequency_hz", "sample_rate_hz", "amplitude", "phase_rad", "alias_frequency_hz",
    "sampling_state", "sample_rms", "peak_frequency_hz", "reconstruction_rmse", "warnings",
]


class EvidenceRef(FrozenRecord):
    run_id: str
    metric_key: EvidenceKey


class TutorRequest(FrozenRecord):
    session_id: UUID4
    run_id: UUID4
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)]
    prediction: AssessmentAnswer | None = None
    mode: Literal["B", "C"] = "C"


TutorFocus = Literal["sampling", "phase", "interpolation", "smoothness", "post_filter"]


class TutorSelection(FrozenRecord):
    focus: TutorFocus
    evidence: list[EvidenceRef] = Field(min_length=1, max_length=5)
    next_experiment: ExperimentRequest | None


class TutorReply(FrozenRecord):
    explanation: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1200)]
    evidence: list[EvidenceRef] = Field(max_length=5)
    next_experiment: ExperimentRequest | None
    misconception_code: str | None = Field(max_length=64)
