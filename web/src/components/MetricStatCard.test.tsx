import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MetricStatCard from './MetricStatCard'

describe('MetricStatCard', () => {
  it('formats numeric values with precision and suffix', () => {
    const { container } = render(
      <MetricStatCard
        title="Uptime"
        value={86.712}
        precision={1}
        suffix="%"
        trend={{ direction: 'up', good: true, label: 'vs 85 target' }}
        definition="Share of observed productive time."
      />,
    )
    expect(container.textContent).toContain('86.7')
    expect(container.textContent).toContain('%')
    expect(screen.getByText('vs 85 target')).toBeInTheDocument()
    expect(screen.getByText('Uptime')).toBeInTheDocument()
  })

  it('renders n/a for missing values', () => {
    render(<MetricStatCard title="MTTR" value={null} suffix=" h" />)
    expect(screen.getByText('n/a')).toBeInTheDocument()
  })

  it('renders down trends in the danger colour when movement is bad', () => {
    const { container } = render(
      <MetricStatCard
        title="Throughput"
        value={40}
        trend={{ direction: 'down', good: false, label: '6.0% vs prior 7 days' }}
      />,
    )
    const trend = screen.getByText(/6.0% vs prior 7 days/)
    expect(trend.className).toContain('ant-typography-danger')
    expect(container.textContent).toContain('40')
  })
})
