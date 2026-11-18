import { useMemo } from 'react'
import type { EChartsOption } from 'echarts'
import ReactECharts from 'echarts-for-react'
import type { HeatmapResponse } from '../api/types'
import { useTheme } from '../layout/ThemeProvider'
import { chartPalette, tooltipStyle } from './chartTheme'
import type { ChartTheme } from './chartTheme'

export type HeatmapMode = 'shift' | 'fault'

/** Build the tool × shift (or tool × fault code) fault-count heatmap option. */
export function buildHeatmapOption(
  data: HeatmapResponse,
  theme: ChartTheme,
  mode: HeatmapMode = 'shift',
): EChartsOption {
  const palette = chartPalette(theme)
  const xLabels = data.tools
  const yLabels = mode === 'shift' ? data.shifts : data.fault_codes
  const matrix = mode === 'shift' ? data.tool_shift : data.tool_fault
  const points: Array<[number, number, number]> = []
  matrix.forEach((row, toolIndex) => {
    row.forEach((value, categoryIndex) => {
      points.push([toolIndex, categoryIndex, value])
    })
  })
  const maxValue = Math.max(1, data.max_count)

  return {
    backgroundColor: 'transparent',
    animation: false,
    textStyle: { color: palette.text },
    tooltip: {
      position: 'top',
      ...tooltipStyle(palette),
      formatter: (params: unknown) => {
        const point = params as { value?: [number, number, number] }
        if (!point.value) return ''
        const [x, y, value] = point.value
        return `${xLabels[x]}<br/>${yLabels[y]}: <b>${value}</b> faults`
      },
    },
    grid: { left: 88, right: 24, top: 16, bottom: 76 },
    xAxis: {
      type: 'category',
      data: xLabels,
      splitArea: { show: true },
      axisLabel: { color: palette.axis, rotate: 30, hideOverlap: true },
      axisLine: { lineStyle: { color: palette.split } },
    },
    yAxis: {
      type: 'category',
      data: yLabels,
      splitArea: { show: true },
      axisLabel: { color: palette.axis, fontSize: mode === 'fault' ? 10 : 12 },
      axisLine: { lineStyle: { color: palette.split } },
    },
    visualMap: {
      min: 0,
      max: maxValue,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      inRange: { color: palette.heatRange },
      textStyle: { color: palette.text },
    },
    series: [
      {
        name: 'Fault count',
        type: 'heatmap',
        data: points,
        label: { show: false },
        emphasis: {
          itemStyle: { shadowBlur: 8, shadowColor: 'rgba(0,0,0,0.35)' },
        },
      },
    ],
  }
}

export interface FaultHeatmapProps {
  data: HeatmapResponse
  mode?: HeatmapMode
  height?: number
}

/** Thin ECharts wrapper for the fault heatmap. */
export default function FaultHeatmap({ data, mode = 'shift', height = 420 }: FaultHeatmapProps) {
  const { mode: themeMode } = useTheme()
  const option = useMemo(
    () => buildHeatmapOption(data, themeMode, mode),
    [data, themeMode, mode],
  )
  return (
    <ReactECharts
      key={`${themeMode}-${mode}`}
      option={option}
      notMerge
      lazyUpdate
      style={{ height, width: '100%' }}
    />
  )
}
