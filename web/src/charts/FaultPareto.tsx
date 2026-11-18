import { useMemo } from 'react'
import type { EChartsOption } from 'echarts'
import ReactECharts from 'echarts-for-react'
import type { ParetoResponse } from '../api/types'
import { useTheme } from '../layout/ThemeProvider'
import { chartPalette, tooltipStyle } from './chartTheme'
import type { ChartTheme } from './chartTheme'

/**
 * Build the fault Pareto: descending bars on the left axis, cumulative percent
 * on the right axis, and an 80% markLine showing where the vital few end.
 */
export function buildParetoOption(
  data: ParetoResponse,
  theme: ChartTheme,
): EChartsOption {
  const palette = chartPalette(theme)
  const codes = data.rows.map((row) => row.fault_code)
  const counts = data.rows.map((row) => row.count)
  const cumulative = data.rows.map((row) => row.cumulative_pct)

  return {
    backgroundColor: 'transparent',
    animation: false,
    textStyle: { color: palette.text },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      ...tooltipStyle(palette),
    },
    legend: {
      data: ['Fault events', 'Cumulative %'],
      textStyle: { color: palette.text },
      top: 0,
    },
    grid: { left: 48, right: 56, top: 44, bottom: 92 },
    xAxis: {
      type: 'category',
      data: codes,
      axisLabel: { color: palette.axis, rotate: 38, hideOverlap: true, fontSize: 10 },
      axisLine: { lineStyle: { color: palette.split } },
    },
    yAxis: [
      {
        type: 'value',
        name: 'Events',
        nameTextStyle: { color: palette.axis },
        axisLabel: { color: palette.axis },
        splitLine: { lineStyle: { color: palette.split } },
      },
      {
        type: 'value',
        name: 'Cumulative %',
        min: 0,
        max: 100,
        nameTextStyle: { color: palette.axis },
        axisLabel: { color: palette.axis, formatter: '{value}%' },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: 'Fault events',
        type: 'bar',
        data: counts,
        barMaxWidth: 28,
        itemStyle: { color: palette.primary, borderRadius: [3, 3, 0, 0] },
      },
      {
        name: 'Cumulative %',
        type: 'line',
        yAxisIndex: 1,
        data: cumulative,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { color: palette.secondary, width: 2 },
        itemStyle: { color: palette.secondary },
        markLine: {
          silent: true,
          symbol: 'none',
          label: { formatter: '80%', position: 'insideEndTop', color: palette.secondary },
          lineStyle: { color: palette.danger, type: 'dashed' },
          data: [{ yAxis: 80 }],
        },
      },
    ],
  }
}

export interface FaultParetoProps {
  data: ParetoResponse
  height?: number
}

/** Thin ECharts wrapper for the fault Pareto. */
export default function FaultPareto({ data, height = 380 }: FaultParetoProps) {
  const { mode } = useTheme()
  const option = useMemo(() => buildParetoOption(data, mode), [data, mode])
  return (
    <ReactECharts
      key={mode}
      option={option}
      notMerge
      lazyUpdate
      style={{ height, width: '100%' }}
    />
  )
}
