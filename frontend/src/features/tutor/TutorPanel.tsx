import { useEffect, useRef, useState } from 'react';
import type { ExperimentRun, SamplingParams } from '../../api';
import { CaseParameters } from '../learning/LearningQuestion';
import { evidenceLabels, evidenceValue } from './evidence';
import type { EvidenceKey } from './evidence';
import './tutor.css';

export type TutorMode = 'B' | 'C';

export interface TutorReply {
  explanation: string;
  evidence: { run_id: string; metric_key: EvidenceKey }[];
  next_experiment: { experiment_type: 'sampling_aliasing'; params: SamplingParams } | null;
}

export interface StudyTutorCall {
  case_id: string;
  run_id: string;
  status: number | null;
  reply: TutorReply | null;
  error_code: string | null;
}

interface Props {
  sessionId: string;
  run: ExperimentRun;
  disabled: boolean;
  mode?: TutorMode;
  study?: {
    call?: StudyTutorCall;
    onPendingChange?: (pending: boolean) => void;
    onSettled: () => void | Promise<void>;
  };
  onEvidence: (key: EvidenceKey) => void;
  onConfirm: (params: SamplingParams) => void;
}

const defaultQuestion = '结合我的预测和这次实验解释现象，并建议一个可验证的对照。';
const invalidReply = '模型反馈未通过证据校验，请重试。';

function studyFailure(status: number) {
  return status === 504 ? '本次 AI 指导超时，记录已保存，可以继续作答。' : '本次 AI 指导未能完成，记录已保存，可以继续作答。';
}

async function requestGuide(sessionId: string, runId: string, message: string, mode: TutorMode, study: boolean, signal: AbortSignal) {
  const response = await fetch('/api/tutor/guide', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, run_id: runId, message, mode }),
    signal: AbortSignal.any([signal, AbortSignal.timeout(33000)]),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    if (study && ['tutor_timeout', 'tutor_unavailable', 'invalid_tutor_reply', 'tutor_interrupted'].includes(data?.detail)) {
      throw new Error(studyFailure(response.status));
    }
    if (response.status === 504) throw new Error('AI 指导超时，请重试。');
    if (data?.detail === 'tutor_call_pending') throw new Error('本次指导仍在生成，可以稍后查看。');
    if (response.status === 409) throw new Error('会话的指导步骤已锁定，请刷新查看记录。');
    if (data?.detail === 'invalid_tutor_reply') throw new Error(invalidReply);
    if (response.status === 404) throw new Error('请先恢复这次实验的学习记录。');
    throw new Error('本地模型暂时不可用。启动模型后可以重试。');
  }
  const reply = await response.json().catch(() => null) as TutorReply | null;
  if (!reply || typeof reply.explanation !== 'string' || !Array.isArray(reply.evidence)) throw new Error(invalidReply);
  const validEvidence = mode === 'B'
    ? reply.evidence.length === 0 && reply.next_experiment === null
    : reply.evidence.length > 0 && reply.evidence.every((item) =>
      item.run_id === runId && Object.hasOwn(evidenceLabels, item.metric_key));
  if (!validEvidence) {
    throw new Error(invalidReply);
  }
  return reply;
}

export function TutorPanel({ sessionId, run, disabled, mode = 'C', study, onEvidence, onConfirm }: Props) {
  const [question, setQuestion] = useState('');
  const [reply, setReply] = useState<TutorReply | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const request = useRef<AbortController | null>(null);
  const saved = study?.call;
  const finished = Boolean(study && (saved?.status != null || reply));
  const visibleReply = saved?.run_id === run.run_id ? saved.reply ?? reply : reply;
  const visibleError = saved?.status && saved.status >= 400 ? studyFailure(saved.status) : error;
  const blocked = disabled || pending || finished;
  useEffect(() => () => request.current?.abort(), []);

  async function ask() {
    if (blocked || request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setPending(true);
    study?.onPendingChange?.(true);
    setReply(null);
    setError(null);
    try {
      const result = await requestGuide(sessionId, run.run_id, question.trim() || defaultQuestion, mode, Boolean(study), controller.signal);
      if (!controller.signal.aborted) setReply(result);
    } catch (failure) {
      if (controller.signal.aborted) return;
      if (failure instanceof DOMException && failure.name === 'TimeoutError') {
        setError('AI 指导超时，请重试。');
      } else if (failure instanceof TypeError) {
        setError('无法连接实验服务，请重试。');
      } else {
        setError(failure instanceof Error ? failure.message : 'AI 指导暂时不可用，请重试。');
      }
    } finally {
      if (!controller.signal.aborted) await study?.onSettled();
      request.current = null;
      study?.onPendingChange?.(false);
      if (!controller.signal.aborted) setPending(false);
    }
  }

  return <section className="panel learning-card tutor-panel" aria-label="本地 AI 指导">
    <h2>本地 AI 指导</h2>
    <p className="case-goal">{study ? '根据本题实验与预测生成一次指导。' : '根据当前实验和已保存预测解释现象。'}</p>
    <form className="learning-form" onSubmit={(event) => { event.preventDefault(); void ask(); }}>
      {!study && <label className="learning-input">你的问题（选填）
        <textarea rows={2} maxLength={400} value={question} placeholder="例如，为什么观测主峰变低了？"
          disabled={blocked} onChange={(event) => setQuestion(event.target.value)} />
      </label>}
      <button type="submit" className="button secondary" disabled={blocked}>获取 AI 指导</button>
    </form>
    {pending && <p role="status">正在生成指导…</p>}
    {saved?.reply && saved.run_id !== run.run_id && <p className="case-goal">本题指导已保存，当前展示对照实验。</p>}
    {visibleError && <p className="request-error" role="alert">{visibleError}</p>}
    {visibleReply && <div className="tutor-reply" aria-live="polite">
      <p>{visibleReply.explanation}</p>
      {visibleReply.evidence.length > 0 && <div className="tutor-evidence" aria-label="引用的实验数据">
        {visibleReply.evidence.map(({ metric_key: key }, index) => <button key={key + index} type="button"
          className="tutor-chip" onClick={() => onEvidence(key)}>
          {evidenceLabels[key]} {evidenceValue(run, key)}
        </button>)}
      </div>}
      {visibleReply.next_experiment && <div className="tutor-proposal">
        <h3>建议对照参数</h3>
        <CaseParameters params={visibleReply.next_experiment.params} />
        <button className="button primary" type="button" disabled={disabled}
          onClick={() => { if (visibleReply.next_experiment) onConfirm(visibleReply.next_experiment.params); }}>
          确认运行对照实验
        </button>
      </div>}
    </div>}
  </section>;
}
