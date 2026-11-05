"""Construct the minimum teaching context and validate model output."""

import asyncio

from pydantic import ValidationError

from app.learning import CASES_BY_ID, LearningCase
from app.schemas import AssessmentAnswer, ExperimentRun, TutorFocus, TutorReply, TutorRequest, TutorSelection
from app.store import Store
from app.tutor.client import TutorClient, TutorTransportError


TIMEOUT_SECONDS = 30
SAMPLING_THEORY = {
    "well_sampled": "本次运行满足充分采样条件。采样率严格大于信号频率的两倍，本实验的周期重建可恢复原正弦。",
    "undersampled": (
        "本次运行属于欠采样。原信号和折叠信号可能产生相同样本，因此这些样本无法唯一确定原信号。"
    ),
    "nyquist_boundary": (
        "本次运行位于奈奎斯特边界。样本取决于初相位，即使观测到主峰，也无法保证唯一恢复原信号。"
    ),
}
FOCUS_GUIDE = {
    "sampling": "",
    "phase": "在两倍采样边界，初相位为零时样本接近零，初相位为 π/2 时样本正负交替。",
    "interpolation": "增加插值点只会从已有样本计算更多绘图点，无法补充独立采样信息。",
    "smoothness": "检验恢复效果时，请比较原信号与重建曲线的误差。光滑且经过样本不足以证明恢复。",
    "post_filter": "频率成分一旦折叠到同一频率，采样后低通无法按原始来源分离它们。",
}
CASE_FOCUS: dict[str, TutorFocus] = {
    "interpolation": "interpolation",
    "smoothness": "smoothness",
    "post-filter": "post_filter",
    "sampling-phase": "phase",
}
METRIC_GUIDE = (
    "理论折叠频率直接读取 run.metrics.alias_frequency_hz，实测主峰读取 run.metrics.peak_frequency_hz。"
    "主峰为空表示没有可辨主峰，理论值仍按记录读取。"
)


class TutorError(RuntimeError):
    def __init__(self, code: str, status: int):
        super().__init__(code)
        self.status = status


def validate_evidence(reply: TutorReply, run: ExperimentRun) -> bool:
    fields = set(run.params.model_dump()) | set(run.metrics.model_dump()) | {"warnings"}
    return bool(reply.evidence) and all(
        item.run_id == run.run_id and item.metric_key in fields for item in reply.evidence
    )


def explain_run(
    run: ExperimentRun, case: LearningCase, answer: AssessmentAnswer | None, focus: TutorFocus,
) -> str:
    params, metrics = run.params, run.metrics
    question = case.prediction
    parts = []
    if params != question.params:
        original = question.params
        parts.append(
            f"原题采样率为 {original.sample_rate_hz} Hz，信号频率为 {original.frequency_hz} Hz，"
            f"振幅为 {original.amplitude:g}，初相位为 {original.phase_rad:.4g} rad。"
        )
    if answer is not None:
        if answer.kind == "numeric":
            parts.append(f"你的原预测是 {answer.value:g} Hz。")
        else:
            label = next((option.label for option in question.options if option.option_id == answer.option_id), answer.option_id)
            parts.append(f"你的原预测是“{label}”。")
    parts.append(
        f"本次采样率为 {params.sample_rate_hz} Hz，信号频率为 {params.frequency_hz} Hz，"
        f"振幅为 {params.amplitude:g}，初相位为 {params.phase_rad:.4g} rad。"
        f"理论折叠频率为 {metrics.alias_frequency_hz:g} Hz。"
    )
    if metrics.peak_frequency_hz is None:
        parts.append("本次样本接近零，未检测到可辨主峰。")
    else:
        parts.append(f"观测主峰为 {metrics.peak_frequency_hz:g} Hz。")
    if focus == "sampling":
        focus = CASE_FOCUS.get(case.case_id, focus)
    parts.extend((SAMPLING_THEORY[metrics.sampling_state], FOCUS_GUIDE[focus]))
    return "".join(parts)


async def guide(request: TutorRequest, store: Store, client: TutorClient | None) -> TutorReply:
    events = store.list_events(str(request.session_id))
    binding = next((event for event in events if event.run_id == request.run_id
                    and event.stage in ("run", "observe")), None)
    if binding is None:
        raise TutorError("tutor_run_not_found", 404)
    run = store.get_run(str(request.run_id))
    if run is None:
        raise TutorError("tutor_run_not_found", 404)
    if run.experiment_type != "sampling_aliasing":
        raise TutorError("tutor_requires_sampling_run", 422)
    if client is None:
        raise TutorError("tutor_unavailable", 502)
    case = CASES_BY_ID[binding.case_id]
    prediction = next((event.answer for event in events if event.case_id == case.case_id
                       and event.stage == "predict"), None)
    context = {
        "run": run.model_dump(mode="json", exclude={"series"}),
        "prediction": prediction.model_dump(mode="json") if prediction else None,
        "exercise": {
            "title": case.title,
            "goal": case.goal,
            "prompt": case.prediction.prompt,
            "params": case.prediction.params.model_dump(mode="json"),
            "options": [option.model_dump(mode="json") for option in case.prediction.options],
        },
        "theory": SAMPLING_THEORY[run.metrics.sampling_state] + METRIC_GUIDE + "".join(FOCUS_GUIDE.values()),
        "message": request.message,
        "mode": request.mode,
    }
    try:
        raw = await asyncio.wait_for(asyncio.to_thread(client.complete, context), TIMEOUT_SECONDS)
    except TimeoutError as error:
        raise TutorError("tutor_timeout", 504) from error
    except TutorTransportError as error:
        raise TutorError("tutor_unavailable", 502) from error
    try:
        if request.mode == "B":
            return TutorReply(explanation=raw, evidence=[], next_experiment=None, misconception_code=None)
        selection = TutorSelection.model_validate_json(raw)
        reply = TutorReply(
            explanation=explain_run(run, case, prediction, selection.focus),
            evidence=selection.evidence, next_experiment=selection.next_experiment, misconception_code=None,
        )
    except ValidationError as error:
        raise TutorError("invalid_tutor_reply", 502) from error
    if not validate_evidence(reply, run):
        raise TutorError("invalid_tutor_reply", 502)
    if reply.next_experiment and reply.next_experiment.params in (run.params, case.transfer.params):
        return reply.model_copy(update={"next_experiment": None})
    return reply
