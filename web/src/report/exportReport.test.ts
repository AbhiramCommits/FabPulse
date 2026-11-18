import { describe, expect, it, vi } from 'vitest'
import { downloadText, reportToCsv, reportToMarkdown } from './exportReport'
import { reportFixture } from '../test/fixtures'

describe('report exporters', () => {
  it('renders Markdown with headline, excursions, Pareto and glossary', () => {
    const text = reportToMarkdown(reportFixture)
    expect(text).toContain('# FabPulse engineer report')
    expect(text).toContain('## Headline KPIs')
    expect(text).toContain('SCANNER-01')
    expect(text).toContain('VAC_LOSS')
    expect(text).toContain('## Glossary')
    expect(text).toContain('UCL / LCL')
  })

  it('renders a tidy CSV with all sections', () => {
    const text = reportToCsv(reportFixture)
    const lines = text.split('\n')
    expect(lines[0]).toBe('section,item,detail,value')
    expect(text).toContain('headline,Uptime')
    expect(text).toContain('excursion')
    expect(text).toContain('glossary,UCL / LCL')
  })

  it('escapes commas and quotes in CSV cells', () => {
    const data = {
      ...reportFixture,
      glossary: [{ term: 'A, B', definition: 'He said "hello"' }],
    }
    const text = reportToCsv(data)
    expect(text).toContain('"A, B"')
    expect(text).toContain('"He said ""hello"""')
  })

  it('triggers a client-side download', () => {
    const createObjectURL = vi.fn(() => 'blob:fabpulse')
    const revokeObjectURL = vi.fn()
    Object.assign(URL, { createObjectURL, revokeObjectURL })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)

    downloadText('report.md', '# hello', 'text/markdown')
    expect(createObjectURL).toHaveBeenCalled()
    expect(click).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:fabpulse')
    click.mockRestore()
  })
})
