"""Public exercises, server-side scoring and learning report serialization."""

import csv
from datetime import UTC, datetime
from io import StringIO
import json
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter

from app.schemas import (
    AssessmentAnswer,
    ChoiceAnswer,
    ExperimentRun,
    FrozenRecord,
    LearningEvent,
    LearningEventRequest,
    NumericAnswer,
    SamplingParams,
    ScoreResult,
)


class LearningOption(FrozenRecord):
    option_id: str
    label: str


class LearningQuestion(FrozenRecord):
    question_id: str
    prompt: str
    params: SamplingParams
    kind: Literal["numeric", "choice"]
    unit: Literal["Hz"] | None = None
    options: tuple[LearningOption, ...] = ()


class LearningCase(FrozenRecord):
    case_id: str
    title: str
    goal: str
    prediction: LearningQuestion
    transfer: LearningQuestion


class AssessmentKey(FrozenRecord):
    answer: AssessmentAnswer
    tolerance: float = 0
    misconception_code: str
    explanation_key: str


_ROOT = Path(__file__).resolve().parents[2]
CASES = TypeAdapter(list[LearningCase]).validate_json(
    (_ROOT / "content" / "cases.json").read_bytes()
)
CASES_BY_ID = {case.case_id: case for case in CASES}
_KEYS = TypeAdapter(dict[str, AssessmentKey]).validate_json(
    (_ROOT / "backend" / "content" / "assessment_keys.json").read_bytes()
)


def score_answer(case_id: str, answer: AssessmentAnswer) -> ScoreResult:
    """Score the registered question identified by its question ID."""
    key = _KEYS[case_id]
    expected = key.answer
    if isinstance(expected, ChoiceAnswer) and isinstance(answer, ChoiceAnswer):
        correct = expected.option_id == answer.option_id
    elif isinstance(expected, NumericAnswer) and isinstance(answer, NumericAnswer):
        correct = expected.unit == answer.unit and abs(expected.value - answer.value) <= key.tolerance
    else:
        raise ValueError("Answer does not match the registered question type")
    return ScoreResult(
        correct=correct,
        misconception_code=None if correct else key.misconception_code,
        explanation_key=key.explanation_key,
    )


def prepare_event(
    request: LearningEventRequest, case: LearningCase, run: ExperimentRun | None
) -> LearningEvent:
    if request.stage == "run" and (run is None or run.params != case.prediction.params):
        raise ValueError("The saved run does not match the exercise parameters")
    if request.stage == "observe" and run is not None and run.params == case.transfer.params:
        raise ValueError("Use different parameters for the comparison run")
    outcome = {
        "predict": "recorded",
        "run": "completed",
        "observe": "completed",
        "reflect": "recorded",
        "export": "completed",
        "error": "failed",
        "transfer": "incorrect",
    }[request.stage]
    if request.answer is not None:
        question = case.prediction if request.stage == "predict" else case.transfer
        if request.answer.kind != question.kind:
            raise ValueError("Answer does not match the question type")
        if isinstance(request.answer, ChoiceAnswer) and request.answer.option_id not in {
            option.option_id for option in question.options
        }:
            raise ValueError("Answer is not a registered option")
        if request.stage == "transfer":
            score = score_answer(question.question_id, request.answer)
            outcome = "correct" if score.correct else "incorrect"
    return LearningEvent(**request.model_dump(), outcome=outcome, timestamp=datetime.now(UTC))


def export_csv(events: list[LearningEvent], runs: dict) -> str:
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=[
        "event_id", "session_id", "case_id", "case_title", "stage", "run_id",
        "question_id", "question_prompt", "question_params", "question_options",
        "answer_kind", "answer_option_id", "answer_value", "answer_unit", "note",
        "elapsed_ms", "outcome", "timestamp", "run_params", "run_metrics",
    ])
    writer.writeheader()
    for event in events:
        row = event.model_dump(mode="json", exclude={"answer"})
        answer = event.answer.model_dump() if event.answer is not None else {}
        run = runs.get(str(event.run_id))
        case = CASES_BY_ID[event.case_id]
        question = {"predict": case.prediction, "transfer": case.transfer}.get(event.stage)
        question_data = question.model_dump(mode="json") if question else {}
        # Keep the raw note in JSON and prevent a spreadsheet from evaluating it.
        if event.note and event.note.lstrip().startswith(("=", "+", "-", "@")):
            row["note"] = "'" + event.note
        writer.writerow({
            **row,
            "case_title": case.title,
            "question_id": question_data.get("question_id"),
            "question_prompt": question_data.get("prompt"),
            "question_params": json.dumps(question_data["params"], ensure_ascii=False) if question else "",
            "question_options": json.dumps(question_data["options"], ensure_ascii=False) if question else "",
            "answer_kind": answer.get("kind"),
            "answer_option_id": answer.get("option_id"),
            "answer_value": answer.get("value"),
            "answer_unit": answer.get("unit"),
            "run_params": json.dumps(run["params"], ensure_ascii=False) if run else "",
            "run_metrics": json.dumps(run["metrics"], ensure_ascii=False) if run else "",
        })
    return "\ufeff" + output.getvalue()
