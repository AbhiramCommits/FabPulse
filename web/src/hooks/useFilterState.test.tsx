import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import {
  DEFAULT_FILTERS,
  filtersFromSearchParams,
  filtersKey,
  filtersToSearchParams,
  useFilterState,
} from './useFilterState'
import type { FilterState } from '../api/types'

const FULL_FILTERS: FilterState = {
  from_date: '2026-10-01',
  to_date: '2026-10-31',
  tool_ids: ['SCANNER-01', 'TRACK-02'],
  tool_family: 'SCANNER',
  fab_site: 'FAB-A',
  shifts: ['A', 'C'],
  metric: 'yield_pct',
}

function wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter initialEntries={['/']}>{children}</MemoryRouter>
}

describe('filter URL encoding', () => {
  it('round-trips a full filter object through search params', () => {
    const encoded = filtersToSearchParams(FULL_FILTERS)
    const decoded = filtersFromSearchParams(encoded)
    expect(decoded).toEqual(FULL_FILTERS)
    expect(filtersToSearchParams(decoded).toString()).toBe(encoded.toString())
  })

  it('returns defaults for an empty URL', () => {
    expect(filtersFromSearchParams(new URLSearchParams())).toEqual(DEFAULT_FILTERS)
  })

  it('accepts repeated and comma-separated values', () => {
    const params = new URLSearchParams()
    params.append('tool_ids', 'SCANNER-01,TRACK-02')
    params.append('tool_ids', 'METRO-03')
    params.append('shifts', 'C')
    const parsed = filtersFromSearchParams(params)
    expect(parsed.tool_ids).toEqual(['METRO-03', 'SCANNER-01', 'TRACK-02'])
    expect(parsed.shifts).toEqual(['C'])
  })

  it('drops invalid metric, dates and shifts', () => {
    const params = new URLSearchParams(
      'metric=hacked&from_date=yesterday&to_date=2026-02-31x&shifts=Z',
    )
    const parsed = filtersFromSearchParams(params)
    expect(parsed.metric).toBe('throughput_wph')
    expect(parsed.from_date).toBeNull()
    expect(parsed.to_date).toBeNull()
    expect(parsed.shifts).toEqual([])
  })

  it('produces a stable cache key independent of object identity', () => {
    expect(filtersKey({ ...FULL_FILTERS })).toBe(filtersKey(FULL_FILTERS))
  })
})

describe('useFilterState', () => {
  it('merges updates into the URL and resets to defaults', () => {
    const view = renderHook(
      () => {
        const state = useFilterState()
        const location = useLocation()
        return { ...state, search: location.search }
      },
      { wrapper },
    )
    expect(view.result.current.filters).toEqual(DEFAULT_FILTERS)
    expect(view.result.current.shareUrl).toContain('/')

    act(() => {
      view.result.current.setFilters({ metric: 'yield_pct', shifts: ['A'] })
    })
    expect(view.result.current.search).toContain('metric=yield_pct')
    expect(view.result.current.search).toContain('shifts=A')
    expect(view.result.current.filters.metric).toBe('yield_pct')

    act(() => {
      view.result.current.setFilters({ tool_ids: ['SCANNER-02'], from_date: '2026-10-01' })
    })
    expect(view.result.current.filters.tool_ids).toEqual(['SCANNER-02'])
    expect(view.result.current.filters.metric).toBe('yield_pct')

    act(() => {
      view.result.current.resetFilters()
    })
    expect(view.result.current.search).toBe('')
    expect(view.result.current.filters).toEqual(DEFAULT_FILTERS)
  })

  it('parses the initial URL on load', () => {
    const initial = `/?${filtersToSearchParams(FULL_FILTERS).toString()}`
    const view = renderHook(() => useFilterState(), {
      wrapper: ({ children }: { children: ReactNode }) => (
        <MemoryRouter initialEntries={[initial]}>{children}</MemoryRouter>
      ),
    })
    expect(view.result.current.filters).toEqual(FULL_FILTERS)
  })
})
