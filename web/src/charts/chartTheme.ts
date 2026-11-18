export type ChartTheme = 'light' | 'dark'

export interface ChartPalette {
  text: string
  axis: string
  split: string
  primary: string
  secondary: string
  accent: string
  band: string
  danger: string
  success: string
  heatRange: string[]
  tooltipBg: string
  tooltipText: string
}

/**
 * Single source of truth for chart colours. Tests assert that switching theme
 * changes the palette, so keep every chart on this function.
 */
export function chartPalette(theme: ChartTheme): ChartPalette {
  if (theme === 'dark') {
    return {
      text: '#e2e8f0',
      axis: '#94a3b8',
      split: '#334155',
      primary: '#2dd4bf',
      secondary: '#fbbf24',
      accent: '#818cf8',
      band: 'rgba(45, 212, 191, 0.12)',
      danger: '#f87171',
      success: '#4ade80',
      heatRange: ['#042f2e', '#0f766e', '#2dd4bf', '#99f6e4'],
      tooltipBg: '#0f172a',
      tooltipText: '#e2e8f0',
    }
  }
  return {
    text: '#1f2937',
    axis: '#64748b',
    split: '#e2e8f0',
    primary: '#0f766e',
    secondary: '#d97706',
    accent: '#4f46e5',
    band: 'rgba(15, 118, 110, 0.08)',
    danger: '#dc2626',
    success: '#16a34a',
    heatRange: ['#e6fffb', '#99f6e4', '#2dd4bf', '#0f766e'],
    tooltipBg: '#ffffff',
    tooltipText: '#1f2937',
  }
}

export function metricLabel(metric: string): string {
  switch (metric) {
    case 'yield_pct':
      return 'Yield (%)'
    case 'wafers_processed':
      return 'Wafers processed'
    case 'availability_pct':
      return 'Availability (%)'
    default:
      return 'Throughput (wph)'
  }
}

export function metricUnit(metric: string): string {
  switch (metric) {
    case 'yield_pct':
    case 'availability_pct':
      return '%'
    case 'wafers_processed':
      return ' wafers'
    default:
      return ' wph'
  }
}

export function tooltipStyle(palette: ChartPalette): Record<string, unknown> {
  return {
    backgroundColor: palette.tooltipBg,
    borderColor: palette.split,
    textStyle: { color: palette.tooltipText, fontSize: 12 },
  }
}
