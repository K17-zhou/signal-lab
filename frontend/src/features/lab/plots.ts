import type { EChartsCoreOption } from 'echarts/core';
import type { ExperimentResult, PlotSeries } from '../../api';

const colors = { reference: '#ff7a15', samples: '#315efb', reconstruction: '#12b5a5' };
const fontFamily = 'Microsoft YaHei, PingFang SC, sans-serif';

function points(series: PlotSeries | undefined, max = Infinity): number[][] {
  if (!series) return [];
  return series.x.flatMap((x, index) => x <= max ? [[x, series.y[index]]] : []);
}

function comparisonLines(input: number[][], output: number[][]) {
  return [
    { name: '滤波前', type: 'line' as const, showSymbol: false, data: input, lineStyle: { color: colors.reference, width: 2 } },
    { name: '滤波后', type: 'line' as const, showSymbol: false, data: output, lineStyle: { color: colors.reconstruction, width: 2, type: 'dashed' as const } },
  ];
}

export function buildPlotOptions(run: ExperimentResult): { time: EChartsCoreOption; frequency: EChartsCoreOption } {
  const get = (name: string) => run.series.find((item) => item.name === name);
  const filtering = run.experiment_type === 'lowpass_filter';
  const timeEnd = filtering ? 0.25 : 0.12;
  const frequencyEnd = filtering ? 200 : run.params.sample_rate_hz / 2;
  const timeAmplitude = filtering ? 2 : run.params.amplitude * 1.3;
  const spectrumAmplitude = filtering ? 1.2 : run.params.amplitude * 1.2;
  const common: EChartsCoreOption = {
    animation: false,
    textStyle: { fontFamily, color: '#45516c' },
    grid: { left: 57, right: 25, top: 20, bottom: 43 },
    tooltip: { trigger: 'axis', confine: true },
  };
  const axis = { type: 'value' as const, axisLine: { lineStyle: { color: '#a5aec1' } }, splitLine: { lineStyle: { color: '#e6eaf1' } }, axisLabel: { color: '#59647a', fontSize: 12 } };
  return {
    time: {
      ...common,
      xAxis: { ...axis, min: 0, max: timeEnd, name: '时间 / s', nameLocation: 'middle', nameGap: 28, axisLabel: { color: '#59647a', formatter: (value: number) => value.toFixed(2) } },
      yAxis: { ...axis, name: '幅度', nameLocation: 'middle', nameGap: 39, min: -timeAmplitude, max: timeAmplitude },
      series: filtering ? comparisonLines(points(get('input'), timeEnd), points(get('filtered'), timeEnd)) : [
        { name: '原信号', type: 'line', showSymbol: false, data: points(get('reference'), 0.12), lineStyle: { color: colors.reference, width: 2 } },
        { name: '周期重建', type: 'line', showSymbol: false, data: points(get('reconstruction'), 0.12), lineStyle: { color: colors.reconstruction, width: 2, type: 'dashed' } },
        { name: '采样点', type: 'scatter', symbolSize: 7, data: points(get('samples'), 0.12), itemStyle: { color: colors.samples, opacity: 1 }, z: 5 },
      ],
    },
    frequency: {
      ...common,
      xAxis: { ...axis, min: 0, max: frequencyEnd, name: '频率 / Hz', nameLocation: 'middle', nameGap: 28 },
      yAxis: { ...axis, min: 0, max: spectrumAmplitude, name: '幅度', nameLocation: 'middle', nameGap: 39 },
      series: filtering ? comparisonLines(points(get('input_spectrum'), frequencyEnd), points(get('filtered_spectrum'), frequencyEnd))
        : [{ name: '单边幅度谱', type: 'line', showSymbol: false, data: points(get('spectrum')), lineStyle: { color: colors.samples, width: 2 }, areaStyle: { color: colors.samples, opacity: 0.04 } }],
    },
  };
}
