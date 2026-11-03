import { useEffect, useMemo, useRef } from 'react';
import * as echarts from 'echarts/core';
import type { EChartsCoreOption } from 'echarts/core';
import { LineChart, ScatterChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { SVGRenderer } from 'echarts/renderers';
import type { ExperimentRun } from '../../api';
import { buildPlotOptions } from './plots';
import { formatFrequency } from './format';

echarts.use([LineChart, ScatterChart, GridComponent, TooltipComponent, SVGRenderer]);

function Plot({ option, label }: { option: EChartsCoreOption; label: string }) {
  const element = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!element.current) return;
    const chart = echarts.init(element.current, undefined, { renderer: 'svg' });
    chart.setOption(option);
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(element.current);
    return () => { observer.disconnect(); chart.dispose(); };
  }, [option]);
  return <div className="plot" ref={element} role="img" aria-label={label} />;
}

export function SignalPlots({ run }: { run: ExperimentRun | null }) {
  const options = useMemo(() => run ? buildPlotOptions(run) : null, [run]);
  return <>
    <section className="chart-panel panel time-chart" aria-labelledby="time-heading">
      <div className="chart-heading"><h2 id="time-heading">时域对比</h2>
        <div className="legend" aria-label="曲线图例"><span className="reference">原信号</span><span className="samples">采样点</span><span className="reconstruction">周期重建</span></div>
      </div>
      {options && run ? <Plot option={options.time} label={`时域对比：原信号${run.params.frequency_hz}Hz，采样率${run.params.sample_rate_hz}Hz`} /> : <div className="plot-empty">运行实验后显示波形。</div>}
      <p className="chart-note">显示前 0.12 秒，计算使用完整 1 秒数据。</p>
    </section>
    <section className="chart-panel panel frequency-chart" aria-labelledby="frequency-heading">
      <div className="chart-heading"><h2 id="frequency-heading">频谱观察</h2></div>
      {options && run ? <Plot option={options.frequency} label={`单边频谱：${run.metrics.peak_frequency_hz === null ? '无有效主峰' : `主峰${formatFrequency(run.metrics.peak_frequency_hz)}Hz`}`} /> : <div className="plot-empty">运行实验后显示频谱。</div>}
    </section>
  </>;
}
