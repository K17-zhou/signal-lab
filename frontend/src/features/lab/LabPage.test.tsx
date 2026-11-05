import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { FilteringRun } from '../../api';
import { buildPlotOptions } from './plots';

// Browser QA checks the actual ECharts drawing; JSDOM tests the real page's
// request ordering, validation and error states without its missing layout APIs.
vi.mock('./SignalPlots', () => ({ SignalPlots: () => <div aria-label="实验图表" /> }));

const aliased = {
  run_id: 'run-A', experiment_type: 'sampling_aliasing', engine_version: 'test-transport',
  params: { frequency_hz: 70, sample_rate_hz: 100, amplitude: 1, phase_rad: 0 }, series: [],
  metrics: { alias_frequency_hz: 30, peak_frequency_hz: 30, sampling_state: 'undersampled', sample_rms: 0.707, reconstruction_rmse: 1 },
  warnings: ['PERIODIC_SIGNAL_MODEL', 'UNDERSAMPLED'],
};
const safe = {
  ...aliased, run_id: 'run-B', params: { ...aliased.params, frequency_hz: 50, sample_rate_hz: 400 },
  metrics: { ...aliased.metrics, alias_frequency_hz: 50, peak_frequency_hz: 50, sampling_state: 'well_sampled', reconstruction_rmse: 0 },
  warnings: ['PERIODIC_SIGNAL_MODEL'],
};
const filtered: FilteringRun = {
  run_id: 'run-filter', experiment_type: 'lowpass_filter', engine_version: 'test-transport',
  params: { cutoff_hz: 60 }, series: [], warnings: [],
  metrics: { gain_20hz: 0.99993001, gain_120hz: 0.0538092, steady_state_start_s: 1, steady_state_end_s: 2 },
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}
function response(value: unknown) {
  return new Response(JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

afterEach(() => vi.unstubAllGlobals());

describe('LabPage', () => {
  it('keeps a zero phase aligned between the numeric input and slider', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(aliased)));
    const { LabPage } = await import('./LabPage');
    render(<LabPage />);
    await screen.findByText('run-A');
    expect(screen.getByRole('spinbutton', { name: '初相位' })).toHaveValue(0);
    expect(screen.getByRole('slider', { name: '初相位滑块' })).toHaveValue('0');
  });

  it('keeps the later run when the earlier request finishes last', async () => {
    const first = deferred<Response>();
    const second = deferred<Response>();
    vi.stubGlobal('fetch', vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise));
    const { LabPage } = await import('./LabPage');
    render(<LabPage />);
    fireEvent.click(screen.getByRole('button', { name: '正常采样' }));
    await act(async () => { second.resolve(response(safe)); });
    expect(await screen.findByText('run-B')).toBeVisible();
    await act(async () => { first.resolve(response(aliased)); });
    expect(screen.getByText('run-B')).toBeVisible();
    expect(screen.queryByText('run-A')).not.toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: '信号频率' })).toHaveValue(50);
    expect(screen.getByRole('spinbutton', { name: '采样率' })).toHaveValue(400);
  });

  it('rejects invalid draft input without replacing the previous valid result', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(aliased));
    vi.stubGlobal('fetch', fetchMock);
    const { LabPage } = await import('./LabPage');
    render(<LabPage />);
    await screen.findByText('run-A');
    fireEvent.change(screen.getByRole('spinbutton', { name: '信号频率' }), { target: { value: '201' } });
    fireEvent.click(screen.getByRole('button', { name: '运行实验' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('信号频率');
    expect(screen.getByText('run-A')).toBeVisible();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('shows a failed calculation explicitly and retains the labeled previous result', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response(aliased)).mockRejectedValueOnce(new Error('offline')));
    const { LabPage } = await import('./LabPage');
    render(<LabPage />);
    await screen.findByText('run-A');
    fireEvent.click(screen.getByRole('button', { name: '正常采样' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('上次成功结果'));
    expect(screen.getByText('run-A')).toBeVisible();
    expect(screen.queryByText('run-B')).not.toBeInTheDocument();
  });

  it('runs the low-pass preset and preserves its last valid result on invalid cutoff input', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(response(aliased)).mockResolvedValueOnce(response(filtered));
    vi.stubGlobal('fetch', fetchMock);
    const { LabPage } = await import('./LabPage');
    render(<LabPage />);
    await screen.findByText('run-A');
    fireEvent.click(screen.getByRole('button', { name: '低通滤波' }));
    await screen.findByText('run-filter');
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      experiment_type: 'lowpass_filter', params: { cutoff_hz: 60 },
    });
    expect(screen.getByRole('region', { name: '实验结果' })).toHaveTextContent('0.0538');
    fireEvent.change(screen.getByRole('spinbutton', { name: '截止频率' }), { target: { value: '500' } });
    fireEvent.click(screen.getByRole('button', { name: '运行实验' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('30 Hz');
    expect(screen.getByText('run-filter')).toBeVisible();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('uses whole-number amplitude bounds for the two-tone time chart', () => {
    expect(buildPlotOptions(filtered).time.yAxis).toMatchObject({ min: -2, max: 2 });
  });
});
