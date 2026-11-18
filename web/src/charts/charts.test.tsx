import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { EChartsOption } from 'echarts'
import { ThemeProvider } from '../layout/ThemeProvider'
import { buildTrendOption, brushRangeToDates } from './TrendChart'
import TrendChart from './TrendChart'
import { buildHeatmapOption } from './FaultHeatmap'
import FaultHeatmap from './FaultHeatmap'
import { buildBoxplotOption } from './ExcursionBoxPlot'
import ExcursionBoxPlot from './ExcursionBoxPlot'
import { buildParetoOption } from './FaultPareto'
import FaultPareto from './FaultPareto'
import { chartPalette, metricLabel, metricUnit, tooltipStyle } from './chartTheme'
import { boxplotFixture, heatmapFixture, paretoFixture, timeseriesFixture } from '../test/fixtures'

const chartCapture = vi.hoisted(() => ({
  props: null as null | {
    option: unknown
    onEvents?: Record<string, (params: unknown) => void>
    style?: unknown
  },
}))

vi.mock('echarts-for-react', () => ({
  default: (props: {
    option: unknown
    onEvents?: Record<string, (params: unknown) => void>
    style?: unknown
  }) => {
    chartCapture.props = props
    return null
  },
}))

interface SeriesShape {
  name?: string
  type?: string
  yAxisIndex?: number
  data?: unknown[]
  lineStyle?: { color?: string }
  markLine?: { data?: Array<{ yAxis?: number }> }
  markPoint?: { data?: unknown[] }
  markArea?: { data?: unknown[] }
}

function seriesOf(option: EChartsOption): SeriesShape[] {
  return option.series as unknown as SeriesShape[]
}

beforeEach(() => {
  chartCapture.props = null
})

describe('buildTrendOption', () => {
  it('builds the trend, rolling mean, control limits and violation marks', () => {
    const option = buildTrendOption(timeseriesFixture, 'light')
    const series = seriesOf(option)
    expect(series).toHaveLength(2)
    expect(series[0].type).toBe('line')
    expect(series[1].name).toBe('Rolling mean')
    const markLine = series[0].markLine?.data ?? []
    expect(markLine.map((line) => line.yAxis)).toEqual([15.02, 11.6, 8.18])
    expect(series[0].markPoint?.data).toHaveLength(1)
    expect(series[0].markArea?.data).toHaveLength(1)

    const xAxis = option.xAxis as unknown as { data: string[] }
    expect(xAxis.data[0]).toBe('2026-01-01')
    const dataZoom = option.dataZoom as unknown as Array<{ type: string }>
    expect(dataZoom.map((zoom) => zoom.type)).toEqual(['inside', 'slider'])
  })

  it('switches the palette with the theme', () => {
    const light = buildTrendOption(timeseriesFixture, 'light')
    const dark = buildTrendOption(timeseriesFixture, 'dark')
    expect(seriesOf(light)[0].lineStyle?.color).toBe(chartPalette('light').primary)
    expect(seriesOf(dark)[0].lineStyle?.color).toBe(chartPalette('dark').primary)
    expect(seriesOf(light)[0].lineStyle?.color).not.toBe(seriesOf(dark)[0].lineStyle?.color)
    expect(optionBackground(light)).toBe('transparent')
    expect(optionBackground(dark)).toBe('transparent')
  })

  it('omits limit marks when the series has no control limits', () => {
    const option = buildTrendOption(
      { ...timeseriesFixture, ucl: null, lcl: null, center: null },
      'light',
    )
    expect(seriesOf(option)[0].markLine).toBeUndefined()
    expect(seriesOf(option)[0].markArea).toBeUndefined()
  })
})

function optionBackground(option: EChartsOption): unknown {
  return option.backgroundColor
}

describe('brushRangeToDates', () => {
  const dates = ['2026-01-01', '2026-01-02', '2026-01-03']

  it('maps category indices to dates', () => {
    expect(brushRangeToDates([0, 2], dates)).toEqual(['2026-01-01', '2026-01-03'])
  })

  it('maps date strings to dates and rejects empty ranges', () => {
    expect(brushRangeToDates(['2026-01-01', '2026-01-03'], dates)).toEqual([
      '2026-01-01',
      '2026-01-03',
    ])
    expect(brushRangeToDates([2, 2], dates)).toBeNull()
    expect(brushRangeToDates(null, dates)).toBeNull()
    expect(brushRangeToDates([0, 1], [])).toBeNull()
  })
})

describe('buildHeatmapOption', () => {
  it('builds a tool × shift heatmap with all cells and a visual map', () => {
    const option = buildHeatmapOption(heatmapFixture, 'light', 'shift')
    const series = seriesOf(option)
    expect(series[0].type).toBe('heatmap')
    expect(series[0].data).toHaveLength(6)
    const visualMap = option.visualMap as unknown as { max: number }
    expect(visualMap.max).toBe(12)
    const yAxis = option.yAxis as unknown as { data: string[] }
    expect(yAxis.data).toEqual(['A', 'B', 'C'])
  })

  it('switches to tool × fault code cells', () => {
    const option = buildHeatmapOption(heatmapFixture, 'dark', 'fault')
    const yAxis = option.yAxis as unknown as { data: string[] }
    expect(yAxis.data).toEqual(['VAC_LOSS', 'TEMP_DRIFT'])
    expect(seriesOf(option)[0].data).toHaveLength(4)
  })

  it('formats heatmap tooltips', () => {
    const option = buildHeatmapOption(heatmapFixture, 'light', 'shift')
    const formatter = (
      option.tooltip as unknown as {
        formatter: (params: unknown) => string
      }
    ).formatter
    expect(formatter({ value: [0, 1, 5] })).toContain('SCANNER-01')
    expect(formatter({ value: [0, 1, 5] })).toContain('5')
    expect(formatter({})).toBe('')
  })
})

describe('buildBoxplotOption', () => {
  it('produces one box per tool plus a scatter of Tukey outliers', () => {
    const option = buildBoxplotOption(boxplotFixture, 'light')
    const series = seriesOf(option)
    expect(series.map((item) => item.type)).toEqual(['boxplot', 'scatter'])
    expect(series[0].data?.[0]).toEqual([1, 3, 5, 7, 10])
    expect(series[1].data).toHaveLength(1)
    const xAxis = option.xAxis as unknown as { data: string[] }
    expect(xAxis.data).toEqual(['SCANNER-01', 'METRO-01'])
  })

  it('formats box and outlier tooltips', () => {
    const option = buildBoxplotOption(boxplotFixture, 'light')
    const formatter = (
      option.tooltip as unknown as {
        formatter: (params: unknown) => string
      }
    ).formatter
    const boxText = formatter({ seriesType: 'boxplot', value: [0, 1, 3, 5, 7, 10] })
    expect(boxText).toContain('median 5.00')
    const outlierText = formatter({
      seriesType: 'scatter',
      value: [0, 14.5],
      name: '2026-01-04',
      tool: 'SCANNER-01',
    })
    expect(outlierText).toContain('outlier 14.50')
    expect(formatter({ seriesType: 'boxplot', value: [] })).toBe('')
  })
})

describe('theme helpers', () => {
  it('returns distinct palettes and tooltip styles per theme', () => {
    expect(chartPalette('light').primary).not.toBe(chartPalette('dark').primary)
    expect(chartPalette('dark').tooltipBg).toBe('#0f172a')
    expect(tooltipStyle(chartPalette('light'))).toMatchObject({ borderColor: '#e2e8f0' })
  })

  it('labels every supported metric', () => {
    expect(metricLabel('throughput_wph')).toContain('Throughput')
    expect(metricLabel('yield_pct')).toContain('Yield')
    expect(metricLabel('wafers_processed')).toContain('Wafers')
    expect(metricLabel('availability_pct')).toContain('Availability')
    expect(metricLabel('other')).toContain('Throughput')
    expect(metricUnit('yield_pct')).toBe('%')
    expect(metricUnit('availability_pct')).toBe('%')
    expect(metricUnit('wafers_processed')).toContain('wafers')
    expect(metricUnit('throughput_wph')).toContain('wph')
  })
})

describe('buildParetoOption', () => {
  it('puts counts on bars, cumulative % on a second axis and marks 80%', () => {
    const option = buildParetoOption(paretoFixture, 'light')
    const series = seriesOf(option)
    expect(series.map((item) => item.type)).toEqual(['bar', 'line'])
    expect(series[1].yAxisIndex).toBe(1)
    expect(series[1].markLine?.data).toEqual([{ yAxis: 80 }])
    const yAxis = option.yAxis as unknown as Array<{ max?: number }>
    expect(yAxis[1].max).toBe(100)
  })
})

describe('chart wrappers', () => {
  it('renders the trend chart, forwards brush events and resizes with theme', () => {
    const onBrush = vi.fn()
    render(
      <ThemeProvider>
        <TrendChart data={timeseriesFixture} onBrush={onBrush} />
      </ThemeProvider>,
    )
    expect(chartCapture.props?.option).toBeTruthy()
    act(() => {
      chartCapture.props?.onEvents?.brushSelected({
        batch: [{ selected: [{ coordRange: [0, 2] }] }],
      })
    })
    expect(onBrush).toHaveBeenCalledWith(['2026-01-01', '2026-01-03'])
  })

  it('ignores brush events when no callback is supplied', () => {
    render(
      <ThemeProvider>
        <TrendChart data={timeseriesFixture} />
      </ThemeProvider>,
    )
    act(() => {
      chartCapture.props?.onEvents?.brushSelected({
        batch: [{ selected: [{ coordRange: [0, 2] }] }],
      })
    })
    expect(chartCapture.props?.option).toBeTruthy()
  })

  it('renders heatmap, box plot and Pareto wrappers', () => {
    render(
      <ThemeProvider>
        <FaultHeatmap data={heatmapFixture} mode="fault" />
        <ExcursionBoxPlot data={boxplotFixture} />
        <FaultPareto data={paretoFixture} />
      </ThemeProvider>,
    )
    expect(screen.queryByTestId('missing')).not.toBeInTheDocument()
    expect(chartCapture.props?.option).toBeTruthy()
  })
})
