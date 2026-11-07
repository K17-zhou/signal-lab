"""Construct the minimum teaching context and validate model output."""

import asyncio
import math
from time import perf_counter

from pydantic import ValidationError

from app.experiments import sampling
from app.learning import CASES, CASES_BY_ID, LearningCase
from app.schemas import (
    AssessmentAnswer, ExperimentRequest, ExperimentRun, StudyTutorCall,
    TutorFocus, TutorMode, TutorReply, TutorRequest, TutorSelection,
)
from app.store import Store
from app.tutor.client import TutorClient, TutorTransportError


TIMEOUT_SECONDS = 30
STUDY_QUESTION = "结合我的预测与本次实验解释观测结果，并提示下一步该观察什么。"
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
PHASE_COMPARISON_CASES = frozenset({
    "sampling-phase", "nyquist-boundary", "study-x-boundary", "study-y-boundary",
})
# Relative to amplitude: well above floating-point noise in the periodic engine,
# well below a meaningful reconstruction error or a visible phase-sample change.
RECOVERY_RELATIVE_RMSE = 1e-8
PHASE_SAMPLE_CHANGE_RELATIVE_RMS = 1e-6


class TutorError(RuntimeError):
    def __init__(self, code: str, status: int):
        super().__init__(code)
        self.status = status


def validate_evidence(reply: TutorReply, run: ExperimentRun) -> bool:
    fields = set(run.params.model_dump()) | set(run.metrics.model_dump()) | {"warnings"}
    return bool(reply.evidence) and all(
        item.run_id == run.run_id and item.metric_key in fields for item in reply.evidence
    )


def _allows_phase_comparison(run: ExperimentRun, case: LearningCase) -> bool:
    return (
        case.case_id in PHASE_COMPARISON_CASES
        and run.params.sample_rate_hz == 2 * run.params.frequency_hz
        and run.metrics.sampling_state == "nyquist_boundary"
    )


def _comparison_guide(run: ExperimentRun, case: LearningCase) -> str:
    params = run.params
    guide = (
        "本次允许的对照目标：固定当前信号频率、振幅和初相位，仅提高采样率，"
        f"新采样率须严格大于 {max(params.sample_rate_hz, 2 * params.frequency_hz)} Hz，"
        "用主峰和重建误差检验充分采样下的原频率。"
    )
    if _allows_phase_comparison(run, case):
        guide += (
            "本题还允许边界相位观察：固定当前频率、采样率和振幅，仅改变初相位，"
            "比较样本取值的变化；这不证明唯一恢复。"
        )
    return guide


def _validated_comparison_goal(
    run: ExperimentRun, case: LearningCase, proposal: ExperimentRequest | None,
) -> str | None:
    """Keep only the model's own isolated, numerically verified teaching control."""
    if proposal is None or proposal.params in (run.params, case.transfer.params):
        return None
    current, proposed = run.params, proposal.params
    if (proposed.frequency_hz != current.frequency_hz
            or proposed.amplitude != current.amplitude):
        return None

    if (proposed.phase_rad == current.phase_rad
            and proposed.sample_rate_hz > max(current.sample_rate_hz, 2 * current.frequency_hz)):
        control = sampling.build_sampling_run(proposed)
        metrics = control.metrics
        if (metrics.sampling_state != "well_sampled"
                or metrics.peak_frequency_hz is None
                or not math.isclose(metrics.peak_frequency_hz, current.frequency_hz, rel_tol=0, abs_tol=1e-9)
                or metrics.reconstruction_rmse > current.amplitude * RECOVERY_RELATIVE_RMSE):
            return None
        return (
            "对照目的：保持信号频率、振幅和初相位不变，仅提高采样率，"
            f"使其严格大于两倍频率（{2 * current.frequency_hz} Hz）。"
            f"周期模型计算验证主峰为 {metrics.peak_frequency_hz:g} Hz，"
            f"重建误差 RMSE 为 {metrics.reconstruction_rmse:.2g}；请运行对照并核对。"
        )

    if (_allows_phase_comparison(run, case)
            and proposed.sample_rate_hz == current.sample_rate_hz
            and proposed.phase_rad != current.phase_rad):
        control = sampling.build_sampling_run(proposed)
        if control.metrics.sampling_state != "nyquist_boundary":
            return None
        before = next(series.y for series in run.series if series.name == "samples")
        after = next(series.y for series in control.series if series.name == "samples")
        sample_change = math.sqrt(sum((a - b) ** 2 for a, b in zip(after, before, strict=True)) / len(before))
        if sample_change <= current.amplitude * PHASE_SAMPLE_CHANGE_RELATIVE_RMS:
            return None
        return (
            "对照目的：保持频率、采样率和振幅不变，仅改变初相位，观察边界样本取值如何变化。"
            "周期模型已验证样本发生变化；采样率仍恰好为两倍频率，"
            "即使出现主峰，也无法保证唯一恢复原信号。"
        )
    return None


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


async def guide(
    request: TutorRequest, store: Store, client: TutorClient | None, *, condition: TutorMode | None = None,
) -> TutorReply:
    if condition is not None and request.mode != condition:
        raise TutorError("tutor_condition_locked", 409)
    session = str(request.session_id)
    events = store.list_events(session)
    binding = next((event for event in events if event.run_id == request.run_id
                    and event.stage in ("run", "observe")), None)
    if binding is None:
        raise TutorError("tutor_run_not_found", 404)
    run = store.get_run(str(request.run_id))
    if run is None:
        raise TutorError("tutor_run_not_found", 404)
    if run.experiment_type != "sampling_aliasing":
        raise TutorError("tutor_requires_sampling_run", 422)
    case = CASES_BY_ID[binding.case_id]
    if condition is None and case not in CASES:
        raise TutorError("tutor_study_assignment_required", 409)
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
        "theory": (SAMPLING_THEORY[run.metrics.sampling_state] + METRIC_GUIDE
                   + "".join(FOCUS_GUIDE.values()) + _comparison_guide(run, case)),
        "message": STUDY_QUESTION if condition is not None else request.message,
        "mode": request.mode,
    }
    if condition is None:
        return await _generate_reply(context, run, case, prediction, client)

    if binding.stage != "run":
        raise TutorError("tutor_initial_run_required", 409)
    prior = store.get_study_tutor_call(session, case.case_id)
    if prior is not None:
        if prior.reply is not None:
            return prior.reply
        if prior.status is None:
            raise TutorError("tutor_call_pending", 409)
        raise TutorError(prior.error_code or "tutor_unavailable", prior.status)
    if any(event.case_id == case.case_id and event.stage == "transfer" for event in events):
        raise TutorError("tutor_case_closed", 409)

    call = StudyTutorCall(case_id=case.case_id, run_id=run.run_id)
    if not store.reserve_study_tutor_call(session, call):
        raise TutorError("tutor_call_pending", 409)
    started = perf_counter()
    reply = None
    status, error_code = 500, "tutor_interrupted"
    try:
        reply = await _generate_reply(context, run, case, prediction, client)
        status, error_code = 200, None
        return reply
    except TutorError as error:
        status, error_code = error.status, str(error)
        raise
    finally:
        saved = store.save_study_tutor_call(session, call.model_copy(update={
            "elapsed_ms": round((perf_counter() - started) * 1000),
            "status": status, "reply": reply, "error_code": error_code,
        }))
        if not saved:
            raise TutorError("tutor_call_closed", 409)


async def _generate_reply(
    context: dict, run: ExperimentRun, case: LearningCase,
    prediction: AssessmentAnswer | None, client: TutorClient | None,
) -> TutorReply:
    if client is None:
        raise TutorError("tutor_unavailable", 502)
    try:
        raw = await asyncio.wait_for(asyncio.to_thread(client.complete, context), TIMEOUT_SECONDS)
    except TimeoutError as error:
        raise TutorError("tutor_timeout", 504) from error
    except TutorTransportError as error:
        raise TutorError("tutor_unavailable", 502) from error
    try:
        if context["mode"] == "B":
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
    goal = _validated_comparison_goal(run, case, reply.next_experiment)
    if goal is None:
        return reply.model_copy(update={"next_experiment": None})
    return reply.model_copy(update={"explanation": reply.explanation + goal})
