import type { SamplingParams } from '../../api';

export type ParamKey = keyof SamplingParams;
export type Draft = Record<ParamKey, string>;

export const DEFAULT_PARAMS: SamplingParams = { frequency_hz: 70, sample_rate_hz: 100, amplitude: 1, phase_rad: 0 };
export const PRESETS = [
  { name: '正常采样', params: { ...DEFAULT_PARAMS, frequency_hz: 50, sample_rate_hz: 400 } },
  { name: '混叠', params: DEFAULT_PARAMS },
  { name: '边界退化', params: { ...DEFAULT_PARAMS, frequency_hz: 50 } },
  { name: 'DC折叠', params: { ...DEFAULT_PARAMS, frequency_hz: 100 } },
];

export const FIELDS: { key: ParamKey; label: string; min: number; max: number; step: number; unit: string; minLabel: string; maxLabel: string }[] = [
  { key: 'frequency_hz', label: '信号频率', min: 5, max: 200, step: 1, unit: 'Hz', minLabel: '5 Hz', maxLabel: '200 Hz' },
  { key: 'sample_rate_hz', label: '采样率', min: 20, max: 1000, step: 1, unit: 'Hz', minLabel: '20 Hz', maxLabel: '1000 Hz' },
  { key: 'amplitude', label: '幅度', min: 0.1, max: 2, step: 0.1, unit: '', minLabel: '0.1', maxLabel: '2.0' },
  { key: 'phase_rad', label: '初相位', min: -Math.PI, max: Math.PI, step: 0.01, unit: 'rad', minLabel: '−π rad', maxLabel: 'π rad' },
];

export function toDraft(params: SamplingParams): Draft {
  return { frequency_hz: String(params.frequency_hz), sample_rate_hz: String(params.sample_rate_hz), amplitude: params.amplitude.toFixed(1), phase_rad: String(params.phase_rad) };
}

export function parseDraft(draft: Draft): SamplingParams {
  const parsed = {} as SamplingParams;
  for (const field of FIELDS) {
    const value = Number(draft[field.key]);
    if (!draft[field.key].trim() || !Number.isFinite(value) || value < field.min || value > field.max || (field.step === 1 && !Number.isInteger(value))) {
      throw new Error(`${field.label}需在 ${field.minLabel} 至 ${field.maxLabel} 之间${field.step === 1 ? '，并使用整数' : ''}。`);
    }
    parsed[field.key] = value;
  }
  return parsed;
}

export function matches(draft: Draft, params: SamplingParams): boolean {
  return FIELDS.every(({ key }) => draft[key].trim() !== '' && Number(draft[key]) === params[key]);
}
