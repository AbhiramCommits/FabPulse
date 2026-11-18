/**
 * Typed fetch wrapper for the FabPulse API.
 *
 * - Arrays become repeated query parameters (FastAPI style).
 * - Empty/null values are omitted so URLs stay shareable and short.
 * - Aborts propagate as DOMException("AbortError") so hooks can ignore them.
 * - Non-2xx responses become ApiError with the backend `detail` message.
 */
import type {
  BoxplotResponse,
  FilterOptionsResponse,
  FilterState,
  HealthResponse,
  HeatmapResponse,
  KpisResponse,
  ParetoResponse,
  ReportResponse,
  ShiftDeltaResponse,
  TimeSeriesResponse,
  ToolEventsResponse,
} from './types'

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

export type QueryValue =
  | string
  | number
  | boolean
  | null
  | undefined
  | ReadonlyArray<string | number>

export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export function buildQuery(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue
    if (Array.isArray(value)) {
      if (value.length === 0) continue
      for (const item of value) search.append(key, String(item))
    } else {
      search.set(key, String(value))
    }
  }
  const query = search.toString()
  return query ? `?${query}` : ''
}

export function filterParams(filters: FilterState): Record<string, QueryValue> {
  return {
    from_date: filters.from_date,
    to_date: filters.to_date,
    tool_ids: filters.tool_ids,
    tool_family: filters.tool_family,
    fab_site: filters.fab_site,
    shifts: filters.shifts,
    metric: filters.metric,
  }
}

export interface RequestOptions {
  params?: Record<string, QueryValue>
  signal?: AbortSignal
}

export async function apiGet<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = `${API_BASE}${path}${buildQuery(options.params ?? {})}`
  const response = await fetch(url, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal: options.signal,
  })
  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`
    try {
      const body = (await response.json()) as { detail?: string }
      if (body?.detail) detail = body.detail
    } catch {
      // Keep the status-based message when the body is not JSON.
    }
    throw new ApiError(response.status, detail)
  }
  return (await response.json()) as T
}

export interface TimeSeriesOptions {
  window?: number
  sigma?: number
}

export interface EventOptions {
  page?: number
  pageSize?: number
  sortBy?: string
  sortDir?: 'asc' | 'desc'
}

export interface KpiOptions {
  page?: number
  pageSize?: number
  sortBy?: string
  sortDir?: 'asc' | 'desc'
}

export const api = {
  health: (signal?: AbortSignal) => apiGet<HealthResponse>('/api/health', { signal }),

  filterOptions: (signal?: AbortSignal) =>
    apiGet<FilterOptionsResponse>('/api/meta/filters', { signal }),

  kpis: (
    filters: FilterState,
    options: KpiOptions = {},
    signal?: AbortSignal,
  ) =>
    apiGet<KpisResponse>('/api/kpis', {
      params: {
        ...filterParams(filters),
        page: options.page ?? 1,
        page_size: options.pageSize ?? 10,
        sort_by: options.sortBy ?? 'tool_id',
        sort_dir: options.sortDir ?? 'asc',
      },
      signal,
    }),

  timeseries: (
    filters: FilterState,
    options: TimeSeriesOptions = {},
    signal?: AbortSignal,
  ) =>
    apiGet<TimeSeriesResponse>('/api/timeseries', {
      params: {
        ...filterParams(filters),
        window: options.window ?? 7,
        sigma: options.sigma ?? 3,
      },
      signal,
    }),

  boxplot: (filters: FilterState, signal?: AbortSignal) =>
    apiGet<BoxplotResponse>('/api/boxplot', { params: filterParams(filters), signal }),

  pareto: (filters: FilterState, signal?: AbortSignal) =>
    apiGet<ParetoResponse>('/api/pareto', { params: filterParams(filters), signal }),

  heatmap: (filters: FilterState, signal?: AbortSignal) =>
    apiGet<HeatmapResponse>('/api/heatmap', { params: filterParams(filters), signal }),

  shiftDeltas: (filters: FilterState, signal?: AbortSignal) =>
    apiGet<ShiftDeltaResponse>('/api/shifts/delta', {
      params: filterParams(filters),
      signal,
    }),

  toolEvents: (
    toolId: string,
    filters: FilterState,
    options: EventOptions = {},
    signal?: AbortSignal,
  ) =>
    apiGet<ToolEventsResponse>(`/api/tools/${encodeURIComponent(toolId)}/events`, {
      params: {
        ...filterParams(filters),
        page: options.page ?? 1,
        page_size: options.pageSize ?? 25,
        sort_by: options.sortBy ?? 'ts',
        sort_dir: options.sortDir ?? 'desc',
      },
      signal,
    }),

  report: (filters: FilterState, signal?: AbortSignal) =>
    apiGet<ReportResponse>('/api/report/summary', {
      params: filterParams(filters),
      signal,
    }),
}
