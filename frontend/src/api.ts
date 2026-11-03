export interface SamplingParams {
  frequency_hz: number;
  sample_rate_hz: number;
  amplitude: number;
  phase_rad: number;
}

export interface PlotSeries {
  name: string;
  domain: 'time' | 'frequency';
  x_unit: string;
  y_unit: string;
  x: number[];
  y: number[];
}

export interface ExperimentRun {
  run_id: string;
  experiment_type: 'sampling_aliasing';
  params: SamplingParams;
  engine_version: string;
  series: PlotSeries[];
  metrics: {
    alias_frequency_hz: number;
    sampling_state: 'well_sampled' | 'undersampled' | 'nyquist_boundary';
    sample_rms: number;
    peak_frequency_hz: number | null;
    reconstruction_rmse: number;
  };
  warnings: string[];
}

export async function runExperiment(params: SamplingParams, signal: AbortSignal): Promise<ExperimentRun> {
  const response = await fetch('/api/experiments/run', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ experiment_type: 'sampling_aliasing', params }), signal,
  });
  if (!response.ok) {
    throw new Error(response.status === 422 ? '参数未通过校验，请检查输入范围。' : '实验服务暂时不可用，请重试。');
  }
  return response.json() as Promise<ExperimentRun>;
}
