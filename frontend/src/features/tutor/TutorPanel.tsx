import { useEffect, useRef, useState } from 'react';
import type { ExperimentRun, SamplingParams } from '../../api';
import { CaseParameters } from '../learning/LearningQuestion';
import { evidenceLabels, evidenceValue } from './evidence';
import type { EvidenceKey } from './evidence';
import './tutor.css';

interface TutorReply {
  explanation: string;
  evidence: { run_id: string; metric_key: EvidenceKey }[];
  next_experiment: { experiment_type: 'sampling_aliasing'; params: SamplingParams } | null;
}

interface Props {
  sessionId: string;
  run: ExperimentRun;
  disabled: boolean;
  onEvidence: (key: EvidenceKey) => void;
  onConfirm: (params: SamplingParams) => void;
}

const defaultQuestion = '结合我的预测和这次实验解释现象，并建议一个可验证的对照。';
const invalidReply = '模型反馈未通过证据校验，请重试。';

async function requestGuide(sessionId: string, runId: string, message: string, signal: AbortSignal) {
  const response = await fetch('/api/tutor/guide', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, run_id: runId, message }),
    signal: AbortSignal.any([signal, AbortSignal.timeout(33000)]),
  });
  if (!response.ok) {
    if (response.status === 504) throw new Error('AI 指导超时，请重试。');
    const data = await response.json().catch(() => null);
    if (data?.detail === 'invalid_tutor_reply') throw new Error(invalidReply);
    if (response.status === 404) throw new Error('请先恢复这次实验的学习记录。');
    throw new Error('本地模型暂时不可用。启动模型后可以重试。');
  }
  const reply = await response.json().catch(() => null) as TutorReply | null;
  if (!reply || typeof reply.explanation !== 'string' || !Array.isArray(reply.evidence)
    || !reply.evidence.length || reply.evidence.some((item) =>
    item.run_id !== runId || !Object.hasOwn(evidenceLabels, item.metric_key))) {
    throw new Error(invalidReply);
  }
  return reply;
}

export function TutorPanel({ sessionId, run, disabled, onEvidence, onConfirm }: Props) {
  const [question, setQuestion] = useState('');
  const [reply, setReply] = useState<TutorReply | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);

  async function ask() {
    if (disabled || request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setPending(true);
    setReply(null);
    setError(null);
    try {
      const result = await requestGuide(sessionId, run.run_id, question.trim() || defaultQuestion, controller.signal);
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
      request.current = null;
      if (!controller.signal.aborted) setPending(false);
    }
  }

  return <section className="panel learning-card tutor-panel" aria-label="本地 AI 指导">
    <h2>本地 AI 指导</h2>
    <p className="case-goal">根据当前实验和已保存预测解释现象。</p>
    <form className="learning-form" onSubmit={(event) => { event.preventDefault(); void ask(); }}>
      <label className="learning-input">你的问题（选填）
        <textarea rows={2} maxLength={400} value={question} placeholder="例如，为什么观测主峰变低了？"
          disabled={disabled || pending} onChange={(event) => setQuestion(event.target.value)} />
      </label>
      <button type="submit" className="button secondary" disabled={disabled || pending}>获取 AI 指导</button>
    </form>
    {pending && <p role="status">正在生成指导…</p>}
    {error && <p className="request-error" role="alert">{error}</p>}
    {reply && <div className="tutor-reply" aria-live="polite">
      <p>{reply.explanation}</p>
      <div className="tutor-evidence" aria-label="引用的实验数据">
        {reply.evidence.map(({ metric_key: key }, index) => <button key={key + index} type="button"
          className="tutor-chip" onClick={() => onEvidence(key)}>
          {evidenceLabels[key]} {evidenceValue(run, key)}
        </button>)}
      </div>
      {reply.next_experiment && <div className="tutor-proposal">
        <h3>建议对照参数</h3>
        <CaseParameters params={reply.next_experiment.params} />
        <button className="button primary" type="button" disabled={disabled}
          onClick={() => { if (reply.next_experiment) onConfirm(reply.next_experiment.params); }}>
          确认运行对照实验
        </button>
      </div>}
    </div>}
  </section>;
}
