import type { ExperimentRun, SamplingParams } from '../../api';

export type AssessmentAnswer = { kind: 'choice'; option_id: string } | { kind: 'numeric'; value: number; unit: 'Hz' };

export interface LearningQuestion {
  question_id: string;
  prompt: string;
  params: SamplingParams;
  kind: AssessmentAnswer['kind'];
  unit: 'Hz' | null;
  options: { option_id: string; label: string }[];
}

export interface LearningCase {
  case_id: string;
  title: string;
  goal: string;
  prediction: LearningQuestion;
  transfer: LearningQuestion;
}

export interface LearningEventDraft {
  event_id: string;
  session_id: string;
  case_id: string;
  stage: 'predict' | 'run' | 'reflect' | 'transfer' | 'error';
  elapsed_ms: number;
  run_id?: string;
  answer?: AssessmentAnswer;
  note?: string;
}

export interface LearningEvent extends Omit<LearningEventDraft, 'run_id' | 'answer' | 'note'> {
  run_id: string | null;
  answer: AssessmentAnswer | null;
  note: string | null;
  outcome: 'recorded' | 'completed' | 'correct' | 'incorrect' | 'failed';
  timestamp: string;
}

export class LearningRequestError extends Error {
  constructor(readonly status: number) {
    super(status === 409 ? '这一步已有保存记录，请刷新页面查看。'
      : status === 422 ? '提交内容不符合当前题目要求。'
      : status === 404 ? '没有找到对应的案例或运行记录。'
      : '学习服务暂时不可用，请稍后重试。');
  }
}

async function requestJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) throw new LearningRequestError(response.status);
  return response.json() as Promise<T>;
}

export async function loadLearning(sessionId: string, signal: AbortSignal) {
  const [cases, history] = await Promise.all([
    requestJson<LearningCase[]>('/api/learning/cases', { signal }),
    requestJson<{ events: LearningEvent[] }>('/api/sessions/' + sessionId + '/events', { signal }),
  ]);
  return { cases, events: history.events };
}

export function loadLearningRun(runId: string, signal: AbortSignal) {
  return requestJson<ExperimentRun>('/api/experiments/' + runId, { signal });
}

export function appendLearningEvent(event: LearningEventDraft) {
  return requestJson<LearningEvent>('/api/events', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(event),
    signal: AbortSignal.timeout(15000),
  });
}
