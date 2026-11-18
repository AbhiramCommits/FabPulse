import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ParetoResponse } from '../api/types'
import { api } from '../api/client'
import {
  errorMessage,
  useBoxplot,
  useHeatmap,
  useKpis,
  useMeta,
  usePareto,
  useReport,
  useShiftDeltas,
  useTimeseries,
  useToolEvents,
} from './useData'
import {
  boxplotFixture,
  eventsFixture,
  filters,
  heatmapFixture,
  kpisFixture,
  metaFixture,
  paretoFixture,
  reportFixture,
  shiftFixture,
  timeseriesFixture,
} from '../test/fixtures'

vi.mock('../api/client', () => ({
  api: {
    filterOptions: vi.fn(),
    kpis: vi.fn(),
    timeseries: vi.fn(),
    boxplot: vi.fn(),
    pareto: vi.fn(),
    heatmap: vi.fn(),
    shiftDeltas: vi.fn(),
    toolEvents: vi.fn(),
    report: vi.fn(),
  },
}))

const mocked = vi.mocked(api)

beforeEach(() => {
  mocked.filterOptions.mockResolvedValue(metaFixture)
  mocked.kpis.mockResolvedValue(kpisFixture)
  mocked.timeseries.mockResolvedValue(timeseriesFixture)
  mocked.boxplot.mockResolvedValue(boxplotFixture)
  mocked.pareto.mockResolvedValue(paretoFixture)
  mocked.heatmap.mockResolvedValue(heatmapFixture)
  mocked.shiftDeltas.mockResolvedValue(shiftFixture)
  mocked.toolEvents.mockResolvedValue(eventsFixture)
  mocked.report.mockResolvedValue(reportFixture)
})

describe('data hooks', () => {
  it('loads every resource through the typed client', async () => {
    const meta = renderHook(() => useMeta())
    const kpis = renderHook(() => useKpis(filters, 1, 10, 'uptime_pct', 'desc'))
    const series = renderHook(() => useTimeseries(filters, 14, 3))
    const boxplot = renderHook(() => useBoxplot(filters))
    const pareto = renderHook(() => usePareto(filters))
    const heatmap = renderHook(() => useHeatmap(filters))
    const shifts = renderHook(() => useShiftDeltas(filters))
    const events = renderHook(() =>
      useToolEvents('SCANNER-01', filters, 2, 25, 'throughput_wph', 'asc'),
    )
    const report = renderHook(() => useReport(filters))

    await waitFor(() => {
      expect(meta.result.current.data).not.toBeNull()
      expect(kpis.result.current.data).not.toBeNull()
      expect(series.result.current.data).not.toBeNull()
      expect(boxplot.result.current.data).not.toBeNull()
      expect(pareto.result.current.data).not.toBeNull()
      expect(heatmap.result.current.data).not.toBeNull()
      expect(shifts.result.current.data).not.toBeNull()
      expect(events.result.current.data).not.toBeNull()
      expect(report.result.current.data).not.toBeNull()
    })

    expect(mocked.kpis).toHaveBeenCalledWith(
      filters,
      { page: 1, pageSize: 10, sortBy: 'uptime_pct', sortDir: 'desc' },
      expect.any(AbortSignal),
    )
    expect(mocked.toolEvents).toHaveBeenCalledWith(
      'SCANNER-01',
      filters,
      { page: 2, pageSize: 25, sortBy: 'throughput_wph', sortDir: 'asc' },
      expect.any(AbortSignal),
    )
    expect(meta.result.current.loading).toBe(false)
  })

  it('exposes errors and supports retry', async () => {
    mocked.kpis.mockRejectedValueOnce(new Error('warehouse down'))
    const view = renderHook(() => useKpis(filters))
    await waitFor(() => expect(view.result.current.error?.message).toBe('warehouse down'))
    expect(view.result.current.loading).toBe(false)
    expect(errorMessage(view.result.current.error)).toBe('warehouse down')

    act(() => view.result.current.reload())
    await waitFor(() => expect(view.result.current.data).not.toBeNull())
    expect(view.result.current.error).toBeNull()
  })

  it('ignores results that resolve after unmount', async () => {
    let resolvePromise: ((value: ParetoResponse) => void) | undefined
    mocked.pareto.mockReturnValueOnce(
      new Promise<ParetoResponse>((resolve) => {
        resolvePromise = resolve
      }),
    )
    const view = renderHook(() => usePareto(filters))
    expect(view.result.current.loading).toBe(true)
    view.unmount()
    await act(async () => {
      resolvePromise?.(paretoFixture)
      await Promise.resolve()
    })
    expect(mocked.pareto).toHaveBeenCalled()
  })

  it('provides a fallback error message', () => {
    expect(errorMessage(null)).toMatch(/Something went wrong/)
  })
})
