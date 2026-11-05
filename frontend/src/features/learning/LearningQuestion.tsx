import { useRef, useState } from 'react';
import type { ExperimentParams } from '../../api';
import type { AssessmentAnswer, LearningQuestion } from './learningApi';

export function elapsedSince(start: number) {
  return Math.max(0, Math.round(performance.now() - start));
}

export function CaseParameters({ params }: { params: ExperimentParams }) {
  if ('cutoff_hz' in params) return <dl className="case-parameters">
    <div><dt>截止频率</dt><dd>{params.cutoff_hz} Hz</dd></div>
    <div><dt>采样率</dt><dd>1000 Hz</dd></div>
    <div><dt>输入分量</dt><dd>20 Hz、120 Hz</dd></div>
    <div><dt>滤波器</dt><dd>四阶低通</dd></div>
  </dl>;
  return <dl className="case-parameters">
    <div><dt>信号频率</dt><dd>{params.frequency_hz} Hz</dd></div>
    <div><dt>采样率</dt><dd>{params.sample_rate_hz} Hz</dd></div>
    <div><dt>幅度</dt><dd>{params.amplitude}</dd></div>
    <div><dt>初相位</dt><dd>{Number(params.phase_rad.toFixed(4))} rad</dd></div>
  </dl>;
}

export function answerText(question: LearningQuestion, answer: AssessmentAnswer) {
  if (answer.kind === 'numeric') return answer.value + (answer.unit === 'ratio' ? ' 倍' : ' Hz');
  return question.options.find((option) => option.option_id === answer.option_id)?.label ?? answer.option_id;
}

interface Props {
  question: LearningQuestion;
  stage: 'predict' | 'transfer';
  disabled: boolean;
  onSave: (answer: AssessmentAnswer, elapsedMs: number) => void;
}

export function QuestionForm({ question, stage, disabled, onSave }: Props) {
  const [value, setValue] = useState('');
  const started = useRef(performance.now());
  const valid = value.trim() !== '' && (question.kind === 'choice' || Number.isFinite(Number(value)));
  const unit = question.unit ?? 'Hz';
  const answerLabel = stage === 'predict' ? '预测答案' : '迁移题答案';
  return <form className="learning-form" onSubmit={(event) => {
    event.preventDefault();
    if (!valid || disabled) return;
    const answer: AssessmentAnswer = question.kind === 'numeric'
      ? { kind: 'numeric', value: Number(value), unit }
      : { kind: 'choice', option_id: value };
    onSave(answer, elapsedSince(started.current));
  }}>
    {question.kind === 'numeric' ? <label className="learning-input">
      {answerLabel}{unit === 'ratio' ? '（幅度比）' : '（Hz）'}
      <input type="number" step="any" inputMode="decimal" value={value}
        onChange={(event) => setValue(event.target.value)} disabled={disabled} />
    </label> : <fieldset disabled={disabled}>
      <legend>请选择一个答案</legend>
      {question.options.map((option) => <label key={option.option_id} className="learning-option">
        <input type="radio" name={question.question_id} value={option.option_id}
          checked={value === option.option_id} onChange={() => setValue(option.option_id)} />
        {option.label}
      </label>)}
    </fieldset>}
    <button className="button primary" type="submit" disabled={!valid || disabled}>
      {stage === 'predict' ? '保存预测' : '提交迁移题'}
    </button>
  </form>;
}
