import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import FilterDrawer from './FilterDrawer'
import { metaFixture } from '../test/fixtures'
import { useFilterState } from '../hooks/useFilterState'

function Harness() {
  const { filters, setFilters, resetFilters } = useFilterState()
  const location = useLocation()
  return (
    <>
      <FilterDrawer
        open
        onClose={() => undefined}
        filters={filters}
        meta={metaFixture}
        onApply={setFilters}
        onReset={resetFilters}
      />
      <div data-testid="search">{location.search}</div>
    </>
  )
}

function renderHarness(initial = '/') {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Harness />
    </MemoryRouter>,
  )
}

describe('FilterDrawer', () => {
  it('applies the metric and shift filters to the URL', async () => {
    const user = userEvent.setup()
    renderHarness()

    await user.click(screen.getByText('Yield (%)'))
    await user.click(screen.getByText('B · 14:00–22:00'))
    await user.click(screen.getByRole('button', { name: 'Apply filters' }))

    await waitFor(() => {
      const search = screen.getByTestId('search').textContent ?? ''
      expect(search).toContain('metric=yield_pct')
      expect(search).toContain('shifts=B')
    })
  })

  it('resets the URL to the default filter set', async () => {
    const user = userEvent.setup()
    renderHarness('/?metric=yield_pct&shifts=A')

    expect(screen.getByTestId('search').textContent).toContain('metric=yield_pct')
    await user.click(screen.getByRole('button', { name: 'Reset' }))
    await waitFor(() => expect(screen.getByTestId('search').textContent).toBe(''))
  })

  it('shows the available date window and tool options', async () => {
    const user = userEvent.setup()
    renderHarness()
    expect(screen.getByText(/Available data: 2026-01-01/)).toBeInTheDocument()
    await user.click(screen.getByLabelText('Tools'))
    expect(await screen.findByText('SCANNER-01 · FAB-A')).toBeInTheDocument()
  })
})
