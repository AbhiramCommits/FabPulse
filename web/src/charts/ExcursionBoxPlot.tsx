import { useMemo } from 'react'
import type { EChartsOption } from 'echarts'
import ReactECharts from 'echarts-for-react'
import type { BoxplotResponse } from '../api/types'
import { useTheme } from '../layout/ThemeProvider'
import { chartPalette, metricLabel, tooltipStyle } from './chartTheme'
import type { ChartTheme } from './chartTheme'

/**
 * Build the per-tool box plot from five-number summaries plus a scatter series
 * of Tukey 1.5×IQR outliers (each labelled with its observation date).
 */
export function buildBoxplotOption(data: BoxplotResponse, theme: ChartTheme): EChartsOption {
  const palette = chartPalette(theme)
  const tools = data.tools.map((tool) => tool.tool_id)
  const boxes = data.tools.map((tool) => [tool.min, tool.q1, tool.median, tool.q3, tool.max])
  const outliers = data.tools.flatMap((tool, toolIndex) =>
    tool.outliers.map((outlier) => ({
      value: [toolIndex, outlier.value],
      name: outlier.date,
      tool: tool.tool_id,
    })),
  )

  return {
    backgroundColor: 'transparent',
    animation: false,
    textStyle: { color: palette.text },
    tooltip: {
      trigger: 'item',
      ...tooltipStyle(palette),
      formatter: (params: unknown) => {
        const item = params as {
          seriesType?: string
          value?: unknown
          name?: string
          tool?: string
        }
        if (item.seriesType === 'scatter') {
          const value = item.value as [number, number]
          return `${tools[value[0]] ?? item.tool}<br/>outlier ${value[1].toFixed(2)}<br/>${item.name ?? ''}`
        }
        const value = item.value as number[]
        if (!Array.isArray(value) || value.length < 6) return ''
        return [
          `<b>${tools[value[0]]}</b>`,
          `min ${value[1].toFixed(2)}`,
          `Q1 ${value[2].toFixed(2)}`,
          `median ${value[3].toFixed(2)}`,
          `Q3 ${value[4].toFixed(2)}`,
          `max ${value[5].toFixed(2)}`,
        ].join('<br/>')
      },
    },
    grid: { left: 72, right: 24, top: 48, bottom: 84 },
    xAxis: {
      type: 'category',
      data: tools,
      axisLabel: { color: palette.axis, rotate: 30, hideOverlap: true },
      axisLine: { lineStyle: { color: palette.split } },
    },
    yAxis: {
      type: 'value',
      name: metricLabel(data.metric),
      scale: true,
      nameTextStyle: { color: palette.axis },
      axisLabel: { color: palette.axis },
      splitLine: { lineStyle: { color: palette.split } },
    },
    series: [
      {
        name: 'Five-number summary',
        type: 'boxplot',
        data: boxes,
        itemStyle: {
          color: palette.band,
          borderColor: palette.primary,
          borderWidth: 2,
        },
      },
      {
        name: 'Tukey outliers',
        type: 'scatter',
        data: outliers,
        symbolSize: 8,
        itemStyle: { color: palette.danger },
        z: 5,
      },
    ],
  }
}

export interface ExcursionBoxPlotProps {
  data: BoxplotResponse
  height?: number
}

/** Thin ECharts wrapper for the excursion box plot. */
export default function ExcursionBoxPlot({ data, height = 380 }: ExcursionBoxPlotProps) {
  const { mode } = useTheme()
  const option = useMemo(() => buildBoxplotOption(data, mode), [data, mode])
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
