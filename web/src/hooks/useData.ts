import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type {
  BoxplotResponse,
  FilterOptionsResponse,
  FilterState,
  HeatmapResponse,
  KpisResponse,
  ParetoResponse,
  ReportResponse,
  ShiftDeltaResponse,
  TimeSeriesResponse,
  ToolEventsResponse,
} from '../api/types'
import { filtersKey } from './useFilterState'

export interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: Error | null
  reload: () => void
}

/**
 * Generic abortable data hook. The loader is kept in a ref so callers can pass
 * inline closures without triggering an effect loop; `key` decides refetches.
 */
export function useAsyncData<T>(
  key: string,
  loader: (signal: AbortSignal) => Promise<T>,
): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const [nonce, setNonce] = useState(0)
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    loaderRef
      .current(controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return
        setData(result)
        setLoading(false)
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return
        if (cause instanceof DOMException && cause.name === 'AbortError') return
        setError(cause instanceof Error ? cause : new Error(String(cause)))
        setLoading(false)
      })
    return () => controller.abort()
  }, [key, nonce])

  const reload = useCallback(() => setNonce((value) => value + 1), [])
  return { data, loading, error, reload }
}

export function useMeta(): AsyncState<FilterOptionsResponse> {
  return useAsyncData<FilterOptionsResponse>('meta', (signal) => api.filterOptions(signal))
}

export function useKpis(
  filters: FilterState,
  page = 1,
  pageSize = 10,
  sortBy = 'tool_id',
  sortDir: 'asc' | 'desc' = 'asc',
): AsyncState<KpisResponse> {
  const key = `kpis:${filtersKey(filters)}:${page}:${pageSize}:${sortBy}:${sortDir}`
  return useAsyncData<KpisResponse>(key, (signal) =>
    api.kpis(filters, { page, pageSize, sortBy, sortDir }, signal),
  )
}

export function useTimeseries(
  filters: FilterState,
  window = 7,
  sigma = 3,
): AsyncState<TimeSeriesResponse> {
  const key = `timeseries:${filtersKey(filters)}:${window}:${sigma}`
  return useAsyncData<TimeSeriesResponse>(key, (signal) =>
    api.timeseries(filters, { window, sigma }, signal),
  )
}

export function useBoxplot(filters: FilterState): AsyncState<BoxplotResponse> {
  const key = `boxplot:${filtersKey(filters)}`
  return useAsyncData<BoxplotResponse>(key, (signal) => api.boxplot(filters, signal))
}

export function usePareto(filters: FilterState): AsyncState<ParetoResponse> {
  const key = `pareto:${filtersKey(filters)}`
  return useAsyncData<ParetoResponse>(key, (signal) => api.pareto(filters, signal))
}

export function useHeatmap(filters: FilterState): AsyncState<HeatmapResponse> {
  const key = `heatmap:${filtersKey(filters)}`
  return useAsyncData<HeatmapResponse>(key, (signal) => api.heatmap(filters, signal))
}

export function useShiftDeltas(filters: FilterState): AsyncState<ShiftDeltaResponse> {
  const key = `shift-delta:${filtersKey(filters)}`
  return useAsyncData<ShiftDeltaResponse>(key, (signal) => api.shiftDeltas(filters, signal))
}

export function useToolEvents(
  toolId: string,
  filters: FilterState,
  page = 1,
  pageSize = 10,
  sortBy = 'ts',
  sortDir: 'asc' | 'desc' = 'desc',
): AsyncState<ToolEventsResponse> {
  const key = `events:${toolId}:${filtersKey(filters)}:${page}:${pageSize}:${sortBy}:${sortDir}`
  return useAsyncData<ToolEventsResponse>(key, (signal) =>
    api.toolEvents(toolId, filters, { page, pageSize, sortBy, sortDir }, signal),
  )
}

export function useReport(filters: FilterState): AsyncState<ReportResponse> {
  const key = `report:${filtersKey(filters)}`
  return useAsyncData<ReportResponse>(key, (signal) => api.report(filters, signal))
}

export function errorMessage(error: Error | null): string {
  return error?.message || 'Something went wrong while loading data.'
}
