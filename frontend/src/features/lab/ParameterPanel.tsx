import type { Draft, ParamKey } from './parameters';
import { FIELDS, FILTER_FIELD } from './parameters';

interface Props {
  draft: Draft;
  pending: boolean;
  onChange: (key: ParamKey, value: string) => void;
  onRun: () => void;
  onReset: () => void;
}

export function ParameterPanel({ draft, pending, onChange, onRun, onReset }: Props) {
  const filtering = 'cutoff_hz' in draft;
  const fields = filtering ? [FILTER_FIELD] : FIELDS;
  const values: Partial<Record<ParamKey, string>> = draft;
  return <form className={`parameter-panel panel${filtering ? ' filter-parameter-panel' : ''}`} noValidate onSubmit={(event) => { event.preventDefault(); onRun(); }}>
    <h2>实验参数</h2>
    <div className="parameter-fields">
      {fields.map((field) => {
        const value = values[field.key] ?? '';
        const raw = Number(value);
        const sliderValue = value.trim() && Number.isFinite(raw) ? Math.max(field.min, Math.min(field.max, raw)) : field.min;
        return <div className="parameter-field" key={field.key}>
          <div className="field-top">
            <label htmlFor={field.key}>{field.label}</label>
            <div className="field-value">
              <input id={field.key} type="number" value={value} min={field.min} max={field.max} step={field.step}
                onChange={(event) => onChange(field.key, event.target.value)} />
              {field.unit ? <span>{field.unit}</span> : null}
            </div>
          </div>
          <input className="range" aria-label={`${field.label}滑块`} type="range" min={field.min} max={field.max} step={field.step}
            value={sliderValue} onChange={(event) => onChange(field.key, event.target.value)} />
          <div className="field-limits"><span>{field.minLabel}</span><span>{field.maxLabel}</span></div>
        </div>;
      })}
    </div>
    <div className="parameter-actions">
      <button className="button primary" type="submit" aria-busy={pending}>运行实验</button>
      <button className="reset-button" type="button" onClick={onReset}>恢复默认</button>
    </div>
  </form>;
}
