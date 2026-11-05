export interface SamplingParams {
  frequency_hz: number;
  sample_rate_hz: number;
  amplitude: number;
  phase_rad: number;
}

export interface FilteringParams {
  cutoff_hz: number;
}

export type ExperimentParams = SamplingParams | FilteringParams;

export interface PlotSeries {
  name: string;
  domain: 'time' | 'frequency';
  x_unit: string;
  y_unit: string;
  x: number[];
  y: number[];
}

interface SavedRun {
  run_id: string;
  engine_version: string;
  series: PlotSeries[];
  warnings: string[];
}

export interface ExperimentRun extends SavedRun {
  experiment_type: 'sampling_aliasing';
  params: SamplingParams;
  metrics: {
    alias_frequency_hz: number;
    sampling_state: 'well_sampled' | 'undersampled' | 'nyquist_boundary';
    sample_rms: number;
    peak_frequency_hz: number | null;
    reconstruction_rmse: number;
  };
}

export interface FilteringRun extends SavedRun {
  experiment_type: 'lowpass_filter';
  params: FilteringParams;
  metrics: {
    gain_20hz: number;
    gain_120hz: number;
    steady_state_start_s: number;
    steady_state_end_s: number;
  };
}

export type ExperimentResult = ExperimentRun | FilteringRun;

export async function runExperiment(params: ExperimentParams, signal: AbortSignal): Promise<ExperimentResult> {
  const experiment_type = 'cutoff_hz' in params ? 'lowpass_filter' : 'sampling_aliasing';
  const response = await fetch('/api/experiments/run', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ experiment_type, params }), signal,
  });
  if (!response.ok) {
    throw new Error(response.status === 422 ? '参数未通过校验，请检查输入范围。' : '实验服务暂时不可用，请重试。');
  }
  return response.json() as Promise<ExperimentResult>;
}
