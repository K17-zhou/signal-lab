import type { ExperimentRun } from '../../api';
import { formatFrequency } from './format';

export function RunSummary({ run }: { run: ExperimentRun | null }) {
  if (!run) return <section className="run-summary neutral" aria-label="实验结果"><strong>等待实验结果</strong><p>运行实验后，查看真实计算结果。</p></section>;
  const { metrics, params, warnings } = run;
  const degenerate = warnings.includes('DEGENERATE_SAMPLES');
  const peakLabel = metrics.peak_frequency_hz === null ? '无有效主峰' : `${formatFrequency(metrics.peak_frequency_hz)} Hz`;
  let title = '采样充分';
  let message = `${params.frequency_hz} Hz 信号以 ${params.sample_rate_hz} Hz 采样，当前周期模型可重建。`;
  let tone = 'safe';
  if (metrics.sampling_state === 'nyquist_boundary') {
    title = '奈奎斯特边界'; tone = 'warning';
    message = degenerate ? '当前初相位使采样点接近零，不能据此恢复原信号。' : '采样率恰好为信号频率的两倍，边界处不能保证唯一重建。';
  } else if (metrics.sampling_state === 'undersampled') {
    title = degenerate ? '退化采样' : '发生混叠'; tone = 'warning';
    message = degenerate ? '采样点接近零，原信号的信息已丢失；这不是恢复成功。' : `${params.frequency_hz} Hz 信号以 ${params.sample_rate_hz} Hz 采样，观测到的主峰为 ${peakLabel}。`;
  }
  return <section className={`run-summary ${tone}`} aria-label="实验结果" aria-live="polite">
    <div className="summary-explanation"><strong>{title}</strong><p>{message}</p></div>
    <dl className="metrics">
      <div><dt>原始频率</dt><dd>{params.frequency_hz} <span>Hz</span></dd></div>
      <div><dt>观测主峰</dt><dd>{metrics.peak_frequency_hz === null ? '无有效主峰' : <>{formatFrequency(metrics.peak_frequency_hz)} <span>Hz</span></>}</dd></div>
      <div><dt>重建误差</dt><dd>{metrics.reconstruction_rmse < 0.0005 ? '< 0.001' : metrics.reconstruction_rmse.toFixed(3)}</dd></div>
    </dl>
  </section>;
}
