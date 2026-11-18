import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ToolsPage from './ToolsPage'
import { api } from '../api/client'
import { boxplotFixture, kpisFixture, metaFixture } from '../test/fixtures'

vi.mock('../charts', () => ({
  ExcursionBoxPlot: () => <div>boxplot-mock</div>,
}))

vi.mock('../api/client', () => ({
  api: {
    filterOptions: vi.fn(),
    kpis: vi.fn(),
    boxplot: vi.fn(),
  },
}))

const mocked = vi.mocked(api)

beforeEach(() => {
  mocked.filterOptions.mockResolvedValue(metaFixture)
  mocked.kpis.mockResolvedValue(kpisFixture)
  mocked.boxplot.mockResolvedValue(boxplotFixture)
})

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/tools']}>
      <Routes>
        <Route path="/tools" element={<ToolsPage />} />
        <Route path="/tools/:toolId" element={<div>detail route</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ToolsPage', () => {
  it('renders server-paged KPIs and drills into a tool on row click', async () => {
    const user = userEvent.setup()
    renderPage()

    expect(await screen.findByText('SCANNER-01')).toBeInTheDocument()
    expect(screen.getByText('METRO')).toBeInTheDocument()
    expect(screen.getByText('boxplot-mock')).toBeInTheDocument()

    await user.click(screen.getByText('METRO'))
    expect(await screen.findByText('detail route')).toBeInTheDocument()
  })

  it('shows an error alert when the KPI request is rejected', async () => {
    mocked.kpis.mockRejectedValueOnce(new Error('KPI endpoint exploded'))
    renderPage()

    expect(await screen.findByText('Could not load tool KPIs')).toBeInTheDocument()
    expect(screen.getByText('KPI endpoint exploded')).toBeInTheDocument()
    await waitFor(() => expect(mocked.kpis).toHaveBeenCalled())
  })
})
