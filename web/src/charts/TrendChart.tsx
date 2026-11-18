import { useMemo } from 'react'
import type { EChartsOption } from 'echarts'
import ReactECharts from 'echarts-for-react'
import type { TimeSeriesResponse } from '../api/types'
import { useTheme } from '../layout/ThemeProvider'
import { chartPalette, metricLabel, tooltipStyle } from './chartTheme'
import type { ChartTheme } from './chartTheme'

/**
 * Build the trend chart option: daily metric, rolling mean, UCL/LCL/center
 * markLines, a shaded in-control band, and flagged violation points.
 *
 * Kept pure and exported so Vitest can assert the control-limit values and
 * theme-dependent colours without mounting ECharts.
 */
export function buildTrendOption(
  data: TimeSeriesResponse,
  theme: ChartTheme,
): EChartsOption {
  const palette = chartPalette(theme)
  const dates = data.series.map((point) => point.date)
  const values = data.series.map((point) => point.value)
  const rolling = data.series.map((point) => point.rolling_mean)
  const hasLimits = data.ucl !== null && data.lcl !== null && data.center !== null
  const numericValues = [...values, ...rolling].filter(
    (value): value is number => typeof value === 'number' && Number.isFinite(value),
  )
  let yMin: number | undefined
  let yMax: number | undefined
  if (hasLimits && numericValues.length) {
    const lower = Math.min(...numericValues, data.lcl as number)
    const upper = Math.max(...numericValues, data.ucl as number)
    // Snap to whole units: ECharts renders ugly fractional labels when both
    // bounds are arbitrary floats (a real bug observed during development).
    yMin = Math.floor(lower)
    yMax = Math.ceil(upper)
  }
  const violations = data.out_of_control.map((point) => ({
    name: point.date,
    coord: [point.date, point.value],
    value: point.value,
    itemStyle: { color: palette.danger },
  }))

  return {
    backgroundColor: 'transparent',
    animation: false,
    textStyle: { color: palette.text },
    tooltip: {
      trigger: 'axis',
      ...tooltipStyle(palette),
      valueFormatter: (value) =>
        typeof value === 'number' ? value.toFixed(2) : String(value ?? '–'),
    },
    legend: {
      data: ['Daily', 'Rolling mean'],
      top: 0,
      textStyle: { color: palette.text },
    },
    grid: { left: 56, right: 24, top: 44, bottom: 82 },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: palette.split } },
      axisLabel: { color: palette.axis, hideOverlap: true },
    },
    yAxis: {
      type: 'value',
      name: metricLabel(data.metric),
      nameTextStyle: { color: palette.axis },
      scale: yMin === undefined,
      min: yMin,
      max: yMax,
      axisLabel: { color: palette.axis },
      splitLine: { lineStyle: { color: palette.split } },
    },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      {
        type: 'slider',
        start: 0,
        end: 100,
        bottom: 8,
        height: 22,
        borderColor: palette.split,
        textStyle: { color: palette.axis },
        fillerColor: palette.band,
        handleStyle: { color: palette.primary },
      },
    ],
    toolbox: {
      right: 8,
      top: 0,
      iconStyle: { borderColor: palette.axis },
      feature: {
        brush: { type: ['rect', 'clear'] },
        dataZoom: { yAxisIndex: 'none' },
        restore: {},
      },
    },
    brush: {
      xAxisIndex: 0,
      brushMode: 'single',
      throttleType: 'debounce',
      throttleDelay: 250,
      brushStyle: { borderColor: palette.accent, color: 'rgba(79,70,229,0.08)' },
    },
    series: [
      {
        name: 'Daily',
        type: 'line',
        data: values,
        symbol: 'none',
        connectNulls: false,
        lineStyle: { width: 2, color: palette.primary },
        itemStyle: { color: palette.primary },
        emphasis: { focus: 'series' },
        markLine: hasLimits
          ? {
              silent: true,
              symbol: 'none',
              animation: false,
              label: { color: palette.text, fontSize: 10 },
              data: [
                {
                  yAxis: data.ucl as number,
                  name: 'UCL',
                  label: { formatter: 'UCL' },
                  lineStyle: { color: palette.danger, type: 'dashed', width: 1 },
                },
                {
                  yAxis: data.center as number,
                  name: 'Center',
                  label: { formatter: 'CL' },
                  lineStyle: { color: palette.axis, type: 'dotted', width: 1 },
                },
                {
                  yAxis: data.lcl as number,
                  name: 'LCL',
                  label: { formatter: 'LCL' },
                  lineStyle: { color: palette.danger, type: 'dashed', width: 1 },
                },
              ],
            }
          : undefined,
        markArea: hasLimits
          ? {
              silent: true,
              itemStyle: { color: palette.band },
              data: [
                [
                  { yAxis: data.lcl as number },
                  { yAxis: data.ucl as number },
                ],
              ],
            }
          : undefined,
        markPoint: violations.length
          ? {
              symbol: 'circle',
              symbolSize: 34,
              itemStyle: { color: palette.danger },
              label: { color: '#ffffff', fontSize: 10, formatter: '!' },
              data: violations,
            }
          : undefined,
      },
      {
        name: 'Rolling mean',
        type: 'line',
        data: rolling,
        symbol: 'none',
        smooth: true,
        lineStyle: { width: 2, type: 'dashed', color: palette.accent },
        itemStyle: { color: palette.accent },
      },
    ],
  }
}

/**
 * Translate an ECharts brush `coordRange` into an inclusive ISO date range.
 * Category axes report indices in some ECharts versions and dates in others;
 * both are handled and out-of-range values clamp to the series extent.
 */
export function brushRangeToDates(
  range: unknown,
  dates: string[],
): [string, string] | null {
  if (!Array.isArray(range) || range.length < 2 || dates.length === 0) return null
  const [start, end] = range as [unknown, unknown]
  let fromIndex: number
  let toIndex: number
  if (typeof start === 'number' && typeof end === 'number') {
    fromIndex = Math.max(0, Math.ceil(Math.min(start, end)))
    toIndex = Math.min(dates.length - 1, Math.floor(Math.max(start, end)))
  } else {
    const startIndex = dates.indexOf(String(start))
    const endIndex = dates.indexOf(String(end))
    fromIndex = startIndex >= 0 ? startIndex : 0
    toIndex = endIndex >= 0 ? endIndex : dates.length - 1
  }
  if (toIndex <= fromIndex || !dates[fromIndex] || !dates[toIndex]) return null
  return [dates[fromIndex], dates[toIndex]]
}

export interface TrendChartProps {
  data: TimeSeriesResponse
  height?: number
  onBrush?: (range: [string, string]) => void
}

/** Thin ECharts wrapper; all visual logic lives in `buildTrendOption`. */
export default function TrendChart({ data, height = 380, onBrush }: TrendChartProps) {
  const { mode } = useTheme()
  const option = useMemo(() => buildTrendOption(data, mode), [data, mode])
  const dates = useMemo(() => data.series.map((point) => point.date), [data.series])

  const onEvents = useMemo(
    () => ({
      brushSelected: (params: unknown) => {
        if (!onBrush) return
        const batch = (params as { batch?: Array<{ selected?: Array<{ coordRange?: unknown }> }> })
          .batch
        const range = brushRangeToDates(batch?.[0]?.selected?.[0]?.coordRange, dates)
        if (range) onBrush(range)
      },
    }),
    [dates, onBrush],
  )

  return (
    <ReactECharts
      key={mode}
      option={option}
      notMerge
      lazyUpdate
      style={{ height, width: '100%' }}
      onEvents={onEvents}
    />
  )
}
