import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { runExperiment } from '../../api';
import type { ExperimentParams, ExperimentResult } from '../../api';
import { RunSummary } from '../lab/RunSummary';
import { TutorPanel } from '../tutor/TutorPanel';
import { evidenceLabels, evidenceValue } from '../tutor/evidence';
import type { EvidenceKey } from '../tutor/evidence';
import { answerText, CaseParameters, elapsedSince, QuestionForm } from './LearningQuestion';
import { appendLearningEvent, LearningRequestError, loadLearning, loadLearningRun } from './learningApi';
import type { LearningEventDraft } from './learningApi';
import './learning.css';

const SignalPlots = lazy(() => import('../lab/SignalPlots').then((module) => ({ default: module.SignalPlots })));
const sessionKey = 'signal-lab.learning.session';
const caseKey = 'signal-lab.learning.case';

function newSessionId() {
  const id = crypto.randomUUID();
  sessionStorage.setItem(sessionKey, id);
  sessionStorage.removeItem(caseKey);
  return id;
}

function errorMessage(error: unknown) {
  if (error instanceof DOMException && error.name === 'TimeoutError') return '请求超时，请重试。';
  if (error instanceof TypeError) return '无法连接实验服务，请检查服务是否已启动。';
  return error instanceof Error ? error.message : '操作失败，请重试。';
}

export function LearningFlow({ studySessionId }: { studySessionId?: string } = {}) {
  const assigned = studySessionId !== undefined;
  const [sessionId, setSessionId] = useState(() => studySessionId ?? sessionStorage.getItem(sessionKey) ?? newSessionId());
  return <>
    <header className="topbar">
      <span className="brand">信号实验工坊</span>
      {!assigned && <a className="mode-link" href="#">自由实验</a>}
    </header>
    <main className="page">
      <div className="intro">
        <h1>引导学习</h1>
        <p>先写下预测，再用实验验证，最后尝试一道新参数题。</p>
      </div>
      <LearningSession key={sessionId} sessionId={sessionId} assigned={assigned}
        onNewSession={() => setSessionId(newSessionId())} />
    </main>
  </>;
}

function LearningSession({ sessionId, assigned, onNewSession }: { sessionId: string; assigned: boolean; onNewSession: () => void }) {
  const selectedKey = assigned ? `${caseKey}.${sessionId}` : caseKey;
  const [data, setData] = useState<Awaited<ReturnType<typeof loadLearning>> | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [selected, setSelected] = useState(() => sessionStorage.getItem(selectedKey));
  const [busy, setBusy] = useState(false);
  const [tutorPending, setTutorPending] = useState(false);
  const [retry, setRetry] = useState<LearningEventDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<ExperimentResult | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [runAttempt, setRunAttempt] = useState(0);
  const [highlight, setHighlight] = useState<{ runId: string; key: EvidenceKey } | null>(null);
  const summary = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    loadLearning(sessionId, controller.signal, assigned).then((result) => {
      if (!controller.signal.aborted) setData(result);
    }).catch((failure: unknown) => {
      if (!controller.signal.aborted) setLoadError(errorMessage(failure));
    });
    return () => controller.abort();
  }, [sessionId, assigned, loadAttempt]);

  const exercise = data?.cases.find((item) => item.case_id === selected) ?? data?.cases[0];
  const events = data?.events.filter((event) => event.case_id === exercise?.case_id) ?? [];
  const prediction = events.find((event) => event.stage === 'predict');
  const runId = events.find((event) => event.stage === 'run')?.run_id;
  const observation = events.filter((event) => event.stage === 'observe').at(-1);
  const currentRunId = observation?.run_id ?? runId;
  const transfer = events.find((event) => event.stage === 'transfer');
  const reflections = events.filter((event) => event.stage === 'reflect');
  const displayedRun = run && run.run_id === currentRunId ? run : null;
  const studyCall = data?.tutor_calls?.find((call) => call.case_id === exercise?.case_id);
  const needsGuide = assigned && studyCall?.status == null;
  const locked = busy || tutorPending || retry !== null;

  useEffect(() => {
    if (!currentRunId || currentRunId === run?.run_id) return;
    const controller = new AbortController();
    loadLearningRun(currentRunId, controller.signal).then((result) => {
      if (!controller.signal.aborted) setRun(result);
    }).catch((failure: unknown) => {
      if (!controller.signal.aborted) setRunError(errorMessage(failure));
    });
    return () => controller.abort();
  }, [currentRunId, run?.run_id, runAttempt]);

  if (loadError) return <div className="learning-notice request-error" role="alert">
    <p>{loadError}</p>
    <button className="button secondary" onClick={() => {
      setLoadError(null);
      setLoadAttempt((value) => value + 1);
    }}>重试加载</button>
  </div>;
  if (!data) return <p className="learning-notice" role="status">正在读取学习记录…</p>;
  if (!exercise) return <p className="learning-notice request-error" role="alert">当前没有可用的练习。</p>;
  const caseId = exercise.case_id;

  function makeEvent(
    stage: LearningEventDraft['stage'], elapsedMs: number,
    fields: Pick<LearningEventDraft, 'run_id' | 'answer' | 'note'> = {},
  ): LearningEventDraft {
    return { event_id: crypto.randomUUID(), session_id: sessionId, case_id: caseId, stage, elapsed_ms: elapsedMs, ...fields };
  }

  async function save(draft: LearningEventDraft) {
    try {
      const saved = await appendLearningEvent(draft);
      setRetry(null);
      setData((previous) => previous && !previous.events.some((event) => event.event_id === saved.event_id)
        ? { ...previous, events: [...previous.events, saved] } : previous);
    } catch (failure) {
      setRetry(failure instanceof LearningRequestError && failure.status < 500 ? null : draft);
      throw failure;
    }
  }

  async function perform(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try { await action(); }
    catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }

  async function runCase(params: ExperimentParams, stage: 'run' | 'observe' = 'run') {
    const started = performance.now();
    let result: ExperimentResult;
    try {
      result = await runExperiment(params, AbortSignal.timeout(15000));
    } catch (failure) {
      await save(makeEvent('error', elapsedSince(started), { note: errorMessage(failure) }));
      throw failure;
    }
    await save(makeEvent(stage, elapsedSince(started), { run_id: result.run_id }));
    setRun(result);
  }

  const activeStep = !prediction ? 0 : !runId ? 1 : 2;
  const exportUrl = '/api/sessions/' + sessionId + '/export?format=';

  async function refreshTutorCalls() {
    try {
      const state = await loadLearning(sessionId, AbortSignal.timeout(15000), true);
      setData((current) => current && { ...current, tutor_calls: state.tutor_calls });
    } catch {
      setError('指导记录暂时无法读取，请刷新页面查看。');
    }
  }

  return <>
    <div className="learning-toolbar">
      <label className="case-picker">学习案例
        <select value={caseId} disabled={locked} onChange={(event) => {
          const id = event.target.value;
          sessionStorage.setItem(selectedKey, id);
          setSelected(id);
          setError(null);
          setRunError(null);
        }}>
          {data.cases.map((item) => <option key={item.case_id} value={item.case_id}>{item.title}</option>)}
        </select>
      </label>
      {data.study
        ? <p className="case-goal">第 {data.study.order_index} 轮 · 已完成 {data.events.filter((event) => event.stage === 'transfer').length}/{data.cases.length} 题</p>
        : <button type="button" className="button secondary" disabled={locked} onClick={onNewSession}>新建会话</button>}
      {data.events.length > 0 && <div className="learning-exports">
        <a className="mode-link" href={exportUrl + 'json'}>导出 JSON</a>
        <a className="mode-link" href={exportUrl + 'csv'}>导出 CSV</a>
      </div>}
    </div>
    <ol className="learning-steps" aria-label="学习步骤">
      {['先做预测', '运行实验', '完成迁移题'].map((step, index) => <li key={step}
        aria-current={index === activeStep && !transfer ? 'step' : undefined}
        className={index < activeStep || transfer ? 'done' : index === activeStep ? 'current' : ''}>
        <span>{index < activeStep || transfer ? '✓' : index + 1}</span>{step}
      </li>)}
    </ol>
    {error && <div role="alert" className="request-error learning-notice">
      <p>{error}</p>
      {retry && <button type="button" className="button secondary" disabled={busy}
        onClick={() => void perform(() => save(retry))}>重试保存</button>}
    </div>}
    <div className="learning-layout" aria-busy={busy}>
        <section className="panel learning-card learning-prediction">
          <h2>先做预测</h2>
          <p className="case-goal">{exercise.goal}</p>
          <CaseParameters params={exercise.prediction.params} />
          <p>{exercise.prediction.prompt}</p>
          {prediction?.answer ? <p className="learning-saved">已保存预测：{answerText(exercise.prediction, prediction.answer)}</p>
            : <QuestionForm key={exercise.prediction.question_id} question={exercise.prediction} stage="predict" disabled={locked}
              onSave={(answer, elapsedMs) => void perform(() => save(makeEvent('predict', elapsedMs, { answer })))} />}
          <button type="button" className="button secondary" disabled={!prediction || Boolean(runId) || locked}
            onClick={() => void perform(() => runCase(exercise.prediction.params))}>运行本题实验</button>
        </section>
      <div className="results-column learning-result">
        {displayedRun ? <>
          <div ref={summary} tabIndex={-1} aria-label="当前运行证据">
            {observation && <p className="case-goal">当前图表显示对照实验</p>}
            <RunSummary run={displayedRun} />
            {displayedRun.experiment_type === 'sampling_aliasing' && highlight?.runId === displayedRun.run_id && <p className="tutor-highlight" role="status">
              {evidenceLabels[highlight.key]} · {evidenceValue(displayedRun, highlight.key)}
            </p>}
          </div>
          <Suspense fallback={<div className="chart-loading panel">正在准备实验图表…</div>}>
            <SignalPlots run={displayedRun} />
          </Suspense>
          {displayedRun.experiment_type === 'sampling_aliasing' && <TutorPanel key={displayedRun.run_id} sessionId={sessionId} run={displayedRun}
            disabled={locked || (assigned && Boolean(transfer))} mode={data.study?.condition}
            study={assigned ? { call: studyCall, onPendingChange: setTutorPending, onSettled: refreshTutorCalls } : undefined}
            onEvidence={(key) => {
              setHighlight({ runId: displayedRun.run_id, key });
              summary.current?.focus({ preventScroll: true });
              summary.current?.scrollIntoView?.({ block: 'nearest' });
            }}
            onConfirm={(params) => void perform(() => runCase(params, 'observe'))} />}
          <section className="panel learning-card">
            <p className="learning-run-id">实验记录 <code>{displayedRun.run_id}</code></p>
            <ReflectionForm key={reflections.at(-1)?.event_id ?? displayedRun.run_id} disabled={locked} onSave={(note, elapsedMs) =>
              void perform(() => save(makeEvent('reflect', elapsedMs, { note, run_id: displayedRun.run_id })))} />
            {reflections.map((event) => <p key={event.event_id} className="learning-reflection">{event.note}</p>)}
          </section>
        </> : <section className="panel learning-card learning-empty">
          <h2>实验结果</h2>
          {runError ? <div role="alert"><p>{runError}</p><button className="button secondary"
            onClick={() => { setRunError(null); setRunAttempt((attempt) => attempt + 1); }}>重试读取结果</button></div>
            : <p role="status">{runId || busy ? '正在读取学习步骤…' : '保存预测并运行实验后，波形和频谱会显示在这里。'}</p>}
        </section>}
      </div>
      {runId && <section className="panel learning-card learning-transfer">
        <h2>迁移题</h2>
        {needsGuide ? <p className="case-goal">完成本题指导步骤后显示迁移题。</p> : <>
          <CaseParameters params={exercise.transfer.params} />
          <p>{exercise.transfer.prompt}</p>
          {transfer?.answer ? <>
            <p>本次作答：{answerText(exercise.transfer, transfer.answer)}</p>
            <p role="status" className={transfer.outcome === 'correct' ? 'learning-saved' : 'learning-incorrect'}>
              {transfer.outcome === 'correct' ? '迁移题答对了' : '迁移题答错了'}
            </p>
          </> : <QuestionForm key={exercise.transfer.question_id} question={exercise.transfer} stage="transfer" disabled={locked}
            onSave={(answer, elapsedMs) => void perform(() => save(makeEvent('transfer', elapsedMs, { answer, run_id: runId })))} />}
        </>}
      </section>}
    </div>
  </>;
}

function ReflectionForm({ disabled, onSave }: { disabled: boolean; onSave: (note: string, elapsedMs: number) => void }) {
  const [note, setNote] = useState('');
  const started = useRef(performance.now());
  return <form className="learning-form" onSubmit={(event) => {
    event.preventDefault();
    if (!note.trim() || disabled) return;
    onSave(note, elapsedSince(started.current));
  }}>
    <label className="learning-input">观察记录（选填）
      <textarea rows={3} maxLength={2000} value={note} disabled={disabled} onChange={(event) => setNote(event.target.value)} />
    </label>
    <button className="button secondary" type="submit" disabled={disabled || !note.trim()}>保存观察</button>
  </form>;
}
