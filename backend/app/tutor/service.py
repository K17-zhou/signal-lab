"""Construct the minimum teaching context and validate model output."""

import asyncio

from pydantic import ValidationError

from app.learning import CASES_BY_ID
from app.schemas import ExperimentRun, TutorReply, TutorRequest
from app.store import Store
from app.tutor.client import TutorClient, TutorTransportError


TIMEOUT_SECONDS = 30
THEORY = (
    "周期正弦取样后，折叠频率取到0至采样率的一半。"
    "采样率严格大于信号频率的两倍时，本实验的周期重建可恢复原正弦。"
    "恰好两倍是边界，样本与初相位有关，不能一概保证恢复。"
    "样本接近零时，主峰为空表示没有可辨的峰。理论折叠频率不等于测得主峰。"
    "插值密度和曲线光滑度不增加采样信息。采样后的滤波不能区分折叠到同一频率的成分。"
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


async def guide(request: TutorRequest, store: Store, client: TutorClient | None) -> TutorReply:
    events = store.list_events(str(request.session_id))
    binding = next((event for event in events if event.run_id == request.run_id
                    and event.stage in ("run", "observe")), None)
    if binding is None:
        raise TutorError("tutor_run_not_found", 404)
    run = store.get_run(str(request.run_id))
    if run is None:
        raise TutorError("tutor_run_not_found", 404)
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
        "theory": THEORY,
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
        reply = TutorReply.model_validate_json(raw)
    except ValidationError as error:
        raise TutorError("invalid_tutor_reply", 502) from error
    if not validate_evidence(reply, run):
        raise TutorError("invalid_tutor_reply", 502)
    if reply.next_experiment and reply.next_experiment.params in (run.params, case.transfer.params):
        return reply.model_copy(update={"next_experiment": None})
    return reply
