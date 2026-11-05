import type { ExperimentParams, SamplingParams } from '../../api';

type SamplingKey = keyof SamplingParams;
export type ParamKey = SamplingKey | 'cutoff_hz';
export type Draft = Record<SamplingKey, string> | { cutoff_hz: string };

export const DEFAULT_PARAMS: SamplingParams = { frequency_hz: 70, sample_rate_hz: 100, amplitude: 1, phase_rad: 0 };
export const DEFAULT_FILTER = { cutoff_hz: 60 };
export const PRESETS = [
  { name: '正常采样', params: { ...DEFAULT_PARAMS, frequency_hz: 50, sample_rate_hz: 400 } },
  { name: '混叠', params: DEFAULT_PARAMS },
  { name: '边界退化', params: { ...DEFAULT_PARAMS, frequency_hz: 50 } },
  { name: 'DC折叠', params: { ...DEFAULT_PARAMS, frequency_hz: 100 } },
  { name: '低通滤波', params: DEFAULT_FILTER },
];

interface ParameterField {
  key: ParamKey;
  label: string;
  min: number;
  max: number;
  step: number | 'any';
  unit: string;
  minLabel: string;
  maxLabel: string;
}

export const FIELDS: (ParameterField & { key: SamplingKey })[] = [
  { key: 'frequency_hz', label: '信号频率', min: 5, max: 200, step: 1, unit: 'Hz', minLabel: '5 Hz', maxLabel: '200 Hz' },
  { key: 'sample_rate_hz', label: '采样率', min: 20, max: 1000, step: 1, unit: 'Hz', minLabel: '20 Hz', maxLabel: '1000 Hz' },
  { key: 'amplitude', label: '幅度', min: 0.1, max: 2, step: 0.1, unit: '', minLabel: '0.1', maxLabel: '2.0' },
  { key: 'phase_rad', label: '初相位', min: -Math.PI, max: Math.PI, step: 'any', unit: 'rad', minLabel: '−π rad', maxLabel: 'π rad' },
];
export const FILTER_FIELD: ParameterField = {
  key: 'cutoff_hz', label: '截止频率', min: 30, max: 200, step: 'any', unit: 'Hz', minLabel: '30 Hz', maxLabel: '200 Hz',
};

export function toDraft(params: ExperimentParams): Draft {
  if ('cutoff_hz' in params) return { cutoff_hz: String(params.cutoff_hz) };
  return { frequency_hz: String(params.frequency_hz), sample_rate_hz: String(params.sample_rate_hz), amplitude: params.amplitude.toFixed(1), phase_rad: String(params.phase_rad) };
}

function parseField(field: ParameterField, input: string): number {
  const value = Number(input);
  if (!input.trim() || !Number.isFinite(value) || value < field.min || value > field.max || (field.step === 1 && !Number.isInteger(value))) {
    throw new Error(`${field.label}需在 ${field.minLabel} 至 ${field.maxLabel} 之间${field.step === 1 ? '，并使用整数' : ''}。`);
  }
  return value;
}

export function parseDraft(draft: Draft): ExperimentParams {
  if ('cutoff_hz' in draft) return { cutoff_hz: parseField(FILTER_FIELD, draft.cutoff_hz) };
  const parsed = {} as SamplingParams;
  for (const field of FIELDS) parsed[field.key] = parseField(field, draft[field.key]);
  return parsed;
}

export function matches(draft: Draft, params: ExperimentParams): boolean {
  if ('cutoff_hz' in draft) {
    return 'cutoff_hz' in params && draft.cutoff_hz.trim() !== '' && Number(draft.cutoff_hz) === params.cutoff_hz;
  }
  if ('cutoff_hz' in params) return false;
  return FIELDS.every(({ key }) => draft[key].trim() !== '' && Number(draft[key]) === params[key]);
}
