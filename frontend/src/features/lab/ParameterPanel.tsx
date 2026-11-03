import type { Draft, ParamKey } from './parameters';
import { FIELDS } from './parameters';

interface Props {
  draft: Draft;
  pending: boolean;
  onChange: (key: ParamKey, value: string) => void;
  onRun: () => void;
  onReset: () => void;
}

export function ParameterPanel({ draft, pending, onChange, onRun, onReset }: Props) {
  return <form className="parameter-panel panel" noValidate onSubmit={(event) => { event.preventDefault(); onRun(); }}>
    <h2>实验参数</h2>
    <div className="parameter-fields">
      {FIELDS.map((field) => {
        const raw = Number(draft[field.key]);
        const sliderValue = draft[field.key].trim() && Number.isFinite(raw) ? Math.max(field.min, Math.min(field.max, raw)) : field.min;
        return <div className="parameter-field" key={field.key}>
          <div className="field-top">
            <label htmlFor={field.key}>{field.label}</label>
            <div className="field-value">
              <input id={field.key} type="number" value={draft[field.key]} min={field.min} max={field.max} step={field.key === 'phase_rad' ? 'any' : field.step}
                onChange={(event) => onChange(field.key, event.target.value)} />
              {field.unit ? <span>{field.unit}</span> : null}
            </div>
          </div>
          <input className="range" aria-label={`${field.label}滑块`} type="range" min={field.min} max={field.max} step={field.key === 'phase_rad' ? 'any' : field.step}
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
