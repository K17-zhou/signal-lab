import type { ExperimentRun } from '../../api';
import { formatFrequency } from '../lab/format';

export type EvidenceKey = keyof ExperimentRun['params'] | keyof ExperimentRun['metrics'] | 'warnings';

export const evidenceLabels: Record<EvidenceKey, string> = {
  frequency_hz: '原始频率',
  sample_rate_hz: '采样率',
  amplitude: '幅度',
  phase_rad: '初相位',
  alias_frequency_hz: '理论折叠频率',
  sampling_state: '采样状态',
  sample_rms: '样本均方根',
  peak_frequency_hz: '观测主峰',
  reconstruction_rmse: '重建误差',
  warnings: '实验提示',
};

const samplingLabels = {
  well_sampled: '采样充分',
  undersampled: '欠采样',
  nyquist_boundary: '奈奎斯特边界',
};
const warningLabels: Record<string, string> = {
  PERIODIC_SIGNAL_MODEL: '周期正弦模型',
  UNDERSAMPLED: '欠采样',
  NYQUIST_BOUNDARY: '奈奎斯特边界',
  DEGENERATE_SAMPLES: '样本接近零',
};

export function evidenceValue(run: ExperimentRun, key: EvidenceKey): string {
  if (key === 'warnings') {
    return run.warnings.map((warning) => warningLabels[warning] ?? warning).join('、') || '无';
  }
  if (key === 'sampling_state') return samplingLabels[run.metrics.sampling_state];
  const values = { ...run.params, ...run.metrics };
  const value = values[key];
  if (value === null) return '无有效主峰';
  if (key.endsWith('_hz')) return formatFrequency(value) + ' Hz';
  if (key === 'phase_rad') return formatFrequency(value) + ' rad';
  return value !== 0 && Math.abs(value) < 0.001 ? value.toExponential(2) : formatFrequency(value);
}
