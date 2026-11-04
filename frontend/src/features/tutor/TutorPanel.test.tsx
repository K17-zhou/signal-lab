import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { ExperimentRun } from '../../api';
import { TutorPanel } from './TutorPanel';

const run: ExperimentRun = {
  run_id: 'saved-run', experiment_type: 'sampling_aliasing', engine_version: 'test',
  params: { frequency_hz: 70, sample_rate_hz: 110, amplitude: 1, phase_rad: 0 },
  series: [], warnings: [],
  metrics: {
    alias_frequency_hz: 40, peak_frequency_hz: 40.00000000000001,
    sampling_state: 'undersampled', sample_rms: 0.707, reconstruction_rmse: 1,
  },
};
const next = { ...run.params, sample_rate_hz: 200 };
const reply = {
  explanation: '比较提高采样率前后的观测主峰。',
  evidence: [{ run_id: run.run_id, metric_key: 'peak_frequency_hz' }],
  next_experiment: { experiment_type: 'sampling_aliasing', params: next },
  misconception_code: null,
};

afterEach(() => vi.unstubAllGlobals());

it('displays the real evidence value and runs the proposal only on confirmation', async () => {
  const request = vi.fn(async () => Response.json(reply));
  const confirm = vi.fn();
  const focus = vi.fn();
  vi.stubGlobal('fetch', request);
  render(<TutorPanel sessionId="saved-session" run={run} disabled={false} onEvidence={focus} onConfirm={confirm} />);
  fireEvent.click(screen.getByRole('button', { name: '获取 AI 指导' }));
  expect(await screen.findByText(reply.explanation)).toBeVisible();
  expect(request).toHaveBeenCalledTimes(1);
  expect(confirm).not.toHaveBeenCalled();
  const evidence = screen.getByRole('button', { name: '观测主峰 40 Hz' });
  fireEvent.click(evidence);
  expect(focus).toHaveBeenCalledWith('peak_frequency_hz');
  fireEvent.click(screen.getByRole('button', { name: '确认运行对照实验' }));
  expect(confirm).toHaveBeenCalledWith(next);
});

it('keeps a failed request actionable and shows no experiment suggestion', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => Response.json({ detail: 'tutor_timeout' }, { status: 504 })));
  render(<TutorPanel sessionId="saved-session" run={run} disabled={false} onEvidence={vi.fn()} onConfirm={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: '获取 AI 指导' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('超时');
  expect(screen.queryByRole('button', { name: '确认运行对照实验' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '获取 AI 指导' })).toBeEnabled();
});
