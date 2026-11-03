import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { ExperimentRun } from '../../api';
import { RunSummary } from './RunSummary';

describe('RunSummary', () => {
  it.each(['well_sampled', 'undersampled'] as const)('keeps floating point noise out of %s frequency labels', (state) => {
    const run: ExperimentRun = {
      run_id: 'precise-run', experiment_type: 'sampling_aliasing', engine_version: 'test-transport',
      params: { frequency_hz: state === 'well_sampled' ? 5 : 54, sample_rate_hz: 49, amplitude: 1, phase_rad: 0 },
      series: [], warnings: ['PERIODIC_SIGNAL_MODEL'],
      metrics: { alias_frequency_hz: 5, peak_frequency_hz: 5.000000000000001, sampling_state: state, sample_rms: 0.707, reconstruction_rmse: 0 },
    };
    render(<RunSummary run={run} />);
    const summary = screen.getByRole('region', { name: '实验结果' });
    expect(summary).not.toHaveTextContent('5.000000000000001');
    expect(screen.getByText('观测主峰').nextElementSibling).toHaveTextContent(/^5 Hz$/);
    expect(run.metrics.peak_frequency_hz).toBe(5.000000000000001);
  });
});
