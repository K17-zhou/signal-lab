import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import type { ExperimentParams, ExperimentResult } from '../../api';
import { runExperiment } from '../../api';
import { ParameterPanel } from './ParameterPanel';
import { RunSummary } from './RunSummary';
import { DEFAULT_FILTER, DEFAULT_PARAMS, matches, parseDraft, PRESETS, toDraft } from './parameters';
import type { ParamKey } from './parameters';

const SignalPlots = lazy(() => import('./SignalPlots').then((module) => ({ default: module.SignalPlots })));

export function LabPage() {
  const [draft, setDraft] = useState(() => toDraft(DEFAULT_PARAMS));
  const [latestRun, setRun] = useState<ExperimentResult | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const latestRequest = useRef(0);
  const active = useRef<AbortController | null>(null);
  const filtering = 'cutoff_hz' in draft;
  const experimentType = filtering ? 'lowpass_filter' : 'sampling_aliasing';
  const run = latestRun?.experiment_type === experimentType ? latestRun : null;

  async function execute(params: ExperimentParams) {
    const requestId = ++latestRequest.current;
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setPending(true); setError(null);
    try {
      const result = await runExperiment(params, controller.signal);
      if (requestId === latestRequest.current) setRun(result);
    } catch (failure) {
      if (requestId === latestRequest.current && !controller.signal.aborted) {
        setError(failure instanceof Error && failure.message !== 'Failed to fetch' ? failure.message : '无法连接实验服务，请确认服务已启动。');
      }
    } finally {
      if (requestId === latestRequest.current) setPending(false);
    }
  }

  useEffect(() => {
    void execute(DEFAULT_PARAMS);
    return () => { latestRequest.current += 1; active.current?.abort(); };
  }, []);

  function selectPreset(params: ExperimentParams) {
    setDraft(toDraft(params));
    void execute(params);
  }

  function submitDraft() {
    try { void execute(parseDraft(draft)); }
    catch (failure) { setError(failure instanceof Error ? failure.message : '请检查参数。'); }
  }

  function updateDraft(key: ParamKey, value: string) {
    setDraft((previous) => ({ ...previous, [key]: value }));
    setError(null);
  }

  function exportRun() {
    if (!run) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(run, null, 2)], { type: 'application/json' }));
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = `signal-lab-${run.run_id}.json`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const dirty = run !== null && !matches(draft, run.params);
  return <>
    <header className="topbar">
      <span className="brand">信号实验工坊</span>
      <div className="topbar-actions"><span className="experiment-type">{filtering ? '双频信号实验' : '周期正弦实验'}</span>
        <a className="mode-link" href="#learn">引导学习</a>
        <button type="button" className="button secondary export-button" onClick={exportRun} disabled={!run}>导出本次数据</button>
      </div>
    </header>
    <main className="page">
      <div className="intro">
        <h1>{filtering ? '低通滤波与信号失真' : '采样、混叠与重建'}</h1>
        <p>{filtering ? '调节截止频率，比较 20 Hz 和 120 Hz 分量的幅度变化。' : '调节参数，观察同一个信号如何呈现不同的样子。'}</p>
      </div>
      <nav className="presets" aria-label="标准案例">
        {PRESETS.map((preset) => <button key={preset.name} type="button" aria-pressed={matches(draft, preset.params)}
          className={`preset-button ${matches(draft, preset.params) ? 'selected' : ''}`} onClick={() => selectPreset(preset.params)}>{preset.name}</button>)}
      </nav>
      <div className="lab-layout">
        <ParameterPanel draft={draft} pending={pending} onChange={updateDraft} onRun={submitDraft} onReset={() => selectPreset(filtering ? DEFAULT_FILTER : DEFAULT_PARAMS)} />
        <div className="results-column" aria-busy={pending}>
          {error ? <div className="request-error" role="alert">实验计算失败：{error}{run ? ' 当前图表为上次成功结果。' : ''}</div> : null}
          {pending ? <div className="request-status" role="status">正在计算，完成后更新本次实验结果…</div> : null}
          {!pending && dirty && !error ? <div className="draft-status" role="status">参数已修改，运行实验后更新图表。</div> : null}
          <RunSummary run={run} />
          <Suspense fallback={<div className="chart-loading panel">正在准备实验图表…</div>}><SignalPlots run={run} /></Suspense>
        </div>
      </div>
    </main>
    <footer className="run-record">
      <div><strong>实验记录</strong><code>{run ? run.run_id : '尚未运行'}</code></div>
      <p>{filtering ? '输入包含 20 Hz（幅度 1）和 120 Hz（幅度 0.5），以 1000 Hz 采样 2 秒。' : '当前实验限定为 1 秒周期正弦模型。周期重建不代表能恢复已丢失的信息。'}</p>
    </footer>
  </>;
}
