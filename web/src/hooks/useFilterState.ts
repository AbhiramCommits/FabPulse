import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { FilterState, Metric, ShiftCode } from '../api/types'

export const DEFAULT_FILTERS: FilterState = {
  from_date: null,
  to_date: null,
  tool_ids: [],
  tool_family: null,
  fab_site: null,
  shifts: [],
  metric: 'throughput_wph',
}

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/
const METRICS: Metric[] = [
  'throughput_wph',
  'yield_pct',
  'wafers_processed',
  'availability_pct',
]
const SHIFTS: ShiftCode[] = ['A', 'B', 'C']

function parseDate(value: string | null): string | null {
  if (!value || !DATE_PATTERN.test(value)) return null
  const parsed = new Date(`${value}T00:00:00Z`)
  return Number.isNaN(parsed.getTime()) ? null : value
}

function splitValues(values: string[]): string[] {
  const seen = new Set<string>()
  for (const value of values) {
    for (const part of value.split(',')) {
      const trimmed = part.trim()
      if (trimmed) seen.add(trimmed)
    }
  }
  return Array.from(seen)
}

/**
 * Parse the full filter object from URL search params.
 * Unknown metrics fall back to throughput; invalid dates are discarded.
 */
export function filtersFromSearchParams(params: URLSearchParams): FilterState {
  const metricParam = params.get('metric') as Metric | null
  const metric = metricParam && METRICS.includes(metricParam) ? metricParam : DEFAULT_FILTERS.metric
  const shifts = splitValues(params.getAll('shifts')).filter((value): value is ShiftCode =>
    SHIFTS.includes(value as ShiftCode),
  )
  return {
    from_date: parseDate(params.get('from_date')),
    to_date: parseDate(params.get('to_date')),
    tool_ids: splitValues(params.getAll('tool_ids')).sort(),
    tool_family: params.get('tool_family')?.trim() || null,
    fab_site: params.get('fab_site')?.trim() || null,
    shifts: SHIFTS.filter((shift) => shifts.includes(shift)),
    metric,
  }
}

/** Serialise filters into a stable, shareable set of search params. */
export function filtersToSearchParams(filters: FilterState): URLSearchParams {
  const params = new URLSearchParams()
  if (filters.from_date) params.set('from_date', filters.from_date)
  if (filters.to_date) params.set('to_date', filters.to_date)
  if (filters.tool_ids.length) params.set('tool_ids', filters.tool_ids.join(','))
  if (filters.tool_family) params.set('tool_family', filters.tool_family)
  if (filters.fab_site) params.set('fab_site', filters.fab_site)
  if (filters.shifts.length) params.set('shifts', filters.shifts.join(','))
  if (filters.metric !== DEFAULT_FILTERS.metric) params.set('metric', filters.metric)
  return params
}

/** Stable cache key for data hooks. */
export function filtersKey(filters: FilterState): string {
  return filtersToSearchParams(filters).toString()
}

export interface UseFilterState {
  filters: FilterState
  setFilters: (next: Partial<FilterState>, options?: { replace?: boolean }) => void
  resetFilters: () => void
  shareUrl: string
}

/**
 * URL-backed filter state: every view is shareable by copying the address bar,
 * reloads restore the exact slice, and drill-down links keep the query string.
 */
export function useFilterState(): UseFilterState {
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = useMemo(() => filtersFromSearchParams(searchParams), [searchParams])

  const setFilters = useCallback(
    (next: Partial<FilterState>, options: { replace?: boolean } = {}) => {
      const merged: FilterState = { ...filters, ...next }
      setSearchParams(filtersToSearchParams(merged), { replace: options.replace ?? false })
    },
    [filters, setSearchParams],
  )

  const resetFilters = useCallback(() => {
    setSearchParams(new URLSearchParams(), { replace: false })
  }, [setSearchParams])

  const shareUrl = useMemo(() => {
    if (typeof window === 'undefined') return ''
    return `${window.location.origin}${window.location.pathname}${window.location.search}`
  }, [searchParams])

  return { filters, setFilters, resetFilters, shareUrl }
}
