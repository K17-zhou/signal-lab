import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LearningFlow } from './LearningFlow';

vi.mock('../lab/SignalPlots', () => ({ SignalPlots: () => <div>实验图表</div> }));

const session = '7fbf8d68-4b78-4ea5-9f26-ef1858181cf2';
const params = { frequency_hz: 70, sample_rate_hz: 110, amplitude: 1, phase_rad: 0 };
const exercise = {
  case_id: 'alias-frequency', title: '观察到的频率来自哪里', goal: '对照两种频率。',
  prediction: { question_id: 'alias-predict', kind: 'numeric', unit: 'Hz', options: [], prompt: '预测主峰。', params },
  transfer: { question_id: 'alias-transfer', kind: 'numeric', unit: 'Hz', options: [], prompt: '换一个参数后，新的主峰是多少？', params: { ...params, frequency_hz: 80 } },
};
const run = {
  run_id: '0edb67f5-1fe7-4e65-9a10-5035414b1322',
  experiment_type: 'sampling_aliasing', engine_version: 'test-transport', params, series: [],
  metrics: { alias_frequency_hz: 40, peak_frequency_hz: 40, sampling_state: 'undersampled', sample_rms: 0.707, reconstruction_rmse: 1 },
  warnings: ['PERIODIC_SIGNAL_MODEL', 'UNDERSAMPLED'],
};
const prediction = {
  event_id: '996ece9e-4ac2-4160-9a93-944df77a845f', session_id: session, case_id: exercise.case_id,
  stage: 'predict', answer: { kind: 'numeric', value: 22, unit: 'Hz' }, run_id: null,
  note: null, elapsed_ms: 100, outcome: 'recorded', timestamp: '2026-11-04T12:00:00Z',
};
const savedRun = {
  ...prediction, event_id: '0be4c3d7-9d10-48d4-aa2c-85efc26955d4', stage: 'run',
  answer: null, run_id: run.run_id, outcome: 'completed',
};

function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
}

function setupTransport(history: unknown[] = []) {
  const submitted: Array<Record<string, unknown>> = [];
  const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
    if (url === '/api/learning/cases') return json([exercise]);
    if (url.endsWith('/events') && url !== '/api/events') return json({ session_id: session, events: history });
    if (url === '/api/experiments/run' || url === '/api/experiments/' + run.run_id) return json(run);
    if (url === '/api/events') {
      const payload = JSON.parse(String(options?.body));
      submitted.push(payload);
      const outcome = payload.stage === 'transfer' ? 'correct' : payload.stage === 'run' ? 'completed' : 'recorded';
      return json({ ...payload, outcome, timestamp: prediction.timestamp });
    }
    throw new Error('Unexpected request ' + url);
  });
  vi.stubGlobal('fetch', fetchMock);
  return { submitted, fetchMock };
}

beforeEach(() => {
  sessionStorage.clear();
  sessionStorage.setItem('signal-lab.learning.session', session);
});
afterEach(() => vi.unstubAllGlobals());

describe('guided learning', () => {
  it('saves a prediction before running and then submits a new-parameter question', async () => {
    const { submitted, fetchMock } = setupTransport();
    render(<LearningFlow />);
    const input = await screen.findByRole('spinbutton', { name: '预测答案（Hz）' });
    expect(screen.getByRole('button', { name: '运行本题实验' })).toBeDisabled();
    expect(fetchMock.mock.calls.map(([url]) => url)).not.toContain('/api/experiments/run');
    fireEvent.change(input, { target: { value: '22' } });
    fireEvent.click(screen.getByRole('button', { name: '保存预测' }));
    await screen.findByText('已保存预测：22 Hz');
    fireEvent.click(screen.getByRole('button', { name: '运行本题实验' }));
    const transfer = await screen.findByRole('spinbutton', { name: '迁移题答案（Hz）' });
    expect(screen.getByText('换一个参数后，新的主峰是多少？')).toBeVisible();
    expect(screen.getByText('80 Hz')).toBeVisible();
    fireEvent.change(transfer, { target: { value: '30.5' } });
    fireEvent.click(screen.getByRole('button', { name: '提交迁移题' }));
    expect(await screen.findByText('迁移题答对了')).toBeVisible();
    expect(submitted.map((event) => event.stage)).toEqual(['predict', 'run', 'transfer']);
    expect(submitted[2]).toMatchObject({ run_id: run.run_id, answer: { kind: 'numeric', value: 30.5, unit: 'Hz' } });
  });

  it('restores the original prediction and real run from the same saved session', async () => {
    const { fetchMock } = setupTransport([prediction, savedRun]);
    render(<LearningFlow />);
    expect(await screen.findByText('已保存预测：22 Hz')).toBeVisible();
    expect(await screen.findByText(run.run_id)).toBeVisible();
    expect(screen.queryByRole('button', { name: '保存预测' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '导出 CSV' })).toHaveAttribute('href', '/api/sessions/' + session + '/export?format=csv');
    expect(fetchMock.mock.calls.map(([url]) => url)).toContain('/api/experiments/' + run.run_id);
    expect(fetchMock.mock.calls.map(([url]) => url)).not.toContain('/api/experiments/run');
  });

  it('retries the same event payload when the save response is lost', async () => {
    const { fetchMock, submitted } = setupTransport();
    const transport = fetchMock.getMockImplementation()!;
    let failOnce = true;
    fetchMock.mockImplementation(async (url, options) => {
      if (url === '/api/events' && failOnce) {
        failOnce = false;
        submitted.push(JSON.parse(String(options?.body)));
        throw new TypeError('network unavailable');
      }
      return transport(url, options);
    });
    render(<LearningFlow />);
    fireEvent.change(await screen.findByRole('spinbutton', { name: '预测答案（Hz）' }), { target: { value: '22' } });
    fireEvent.click(screen.getByRole('button', { name: '保存预测' }));
    await screen.findByRole('alert');
    expect(screen.getByRole('button', { name: '运行本题实验' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '重试保存' }));
    await screen.findByText('已保存预测：22 Hz');
    await waitFor(() => expect(submitted).toHaveLength(2));
    expect(submitted[1]).toEqual(submitted[0]);
  });

  it('offers a retry when loading the exercise catalog times out', async () => {
    const { fetchMock } = setupTransport();
    const timeout = new AbortController();
    vi.spyOn(AbortSignal, 'timeout').mockReturnValueOnce(timeout.signal);
    fetchMock.mockImplementationOnce((_url, options) => new Promise((_resolve, reject) => {
      const signal = options?.signal;
      signal?.addEventListener('abort', () => reject(signal.reason), { once: true });
    }));
    render(<LearningFlow />);
    act(() => timeout.abort(new DOMException('Timed out', 'TimeoutError')));
    expect(await screen.findByRole('alert')).toHaveTextContent('请求超时');
    fireEvent.click(screen.getByRole('button', { name: '重试加载' }));
    expect(await screen.findByRole('spinbutton', { name: '预测答案（Hz）' })).toBeVisible();
  });

  it('keeps the prediction and saves a separate run after confirming a tutor proposal', async () => {
    const { fetchMock, submitted } = setupTransport([prediction, savedRun]);
    const originalTransport = fetchMock.getMockImplementation()!;
    const comparison = {
      ...run, run_id: '914ed93e-075c-4bd8-808c-bd6d97409c0f',
      params: { ...params, sample_rate_hz: 200 },
      metrics: { ...run.metrics, sampling_state: 'well_sampled', peak_frequency_hz: 70 },
    };
    fetchMock.mockImplementation(async (url, options) => {
      if (url === '/api/tutor/guide') return json({
        explanation: '提高采样率后再观察主峰。',
        evidence: [{ run_id: run.run_id, metric_key: 'peak_frequency_hz' }],
        next_experiment: { experiment_type: 'sampling_aliasing', params: comparison.params },
      });
      if (url === '/api/experiments/run') {
        expect(JSON.parse(String(options?.body)).params).toEqual(comparison.params);
        return json(comparison);
      }
      return originalTransport(url, options);
    });
    render(<LearningFlow />);
    fireEvent.click(await screen.findByRole('button', { name: '获取 AI 指导' }));
    fireEvent.click(await screen.findByRole('button', { name: '观测主峰 40 Hz' }));
    expect(screen.getByText('观测主峰 · 40 Hz')).toBeVisible();
    expect(submitted).toEqual([]);
    expect(fetchMock.mock.calls.map(([url]) => url)).not.toContain('/api/experiments/run');
    fireEvent.click(screen.getByRole('button', { name: '确认运行对照实验' }));
    expect(await screen.findByText(comparison.run_id)).toBeVisible();
    expect(screen.getByText('当前图表显示对照实验')).toBeVisible();
    expect(screen.getByText('已保存预测：22 Hz')).toBeVisible();
    expect(submitted).toMatchObject([{ stage: 'observe', run_id: comparison.run_id }]);
  });
});
