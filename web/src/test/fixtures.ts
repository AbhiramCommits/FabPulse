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

export const filters: FilterState = {
  from_date: null,
  to_date: null,
  tool_ids: [],
  tool_family: null,
  fab_site: null,
  shifts: [],
  metric: 'throughput_wph',
}

export const metaFixture: FilterOptionsResponse = {
  tools: [
    {
      tool_id: 'SCANNER-01',
      tool_family: 'SCANNER',
      fab_site: 'FAB-A',
      install_date: '2025-01-01',
    },
    { tool_id: 'METRO-01', tool_family: 'METRO', fab_site: 'FAB-A', install_date: '2025-02-01' },
  ],
  families: ['METRO', 'SCANNER'],
  sites: ['FAB-A', 'FAB-B'],
  shifts: [
    { shift_code: 'A', start_hour: 6, end_hour: 14 },
    { shift_code: 'B', start_hour: 14, end_hour: 22 },
    { shift_code: 'C', start_hour: 22, end_hour: 6 },
  ],
  fault_codes: [
    { fault_code: 'VAC_LOSS', fault_category: 'Vacuum', severity: 'HIGH' },
    { fault_code: 'TEMP_DRIFT', fault_category: 'Thermal', severity: 'MEDIUM' },
  ],
  date_bounds: { min_date: '2026-01-01', max_date: '2026-01-10' },
}

const toolKpi = {
  tool_id: 'SCANNER-01',
  tool_family: 'SCANNER',
  fab_site: 'FAB-A',
  events: 1000,
  uptime_pct: 86.7,
  availability_pct: 87.2,
  mtbf_hours: 68.2,
  mttr_hours: 0.93,
  failure_episodes: 12,
  productive_hours: 300,
  unscheduled_down_hours: 12,
  scheduled_down_hours: 4,
  standby_hours: 30,
  engineering_hours: 6,
  wafers: 12000,
  avg_throughput_wph: 50.2,
  avg_yield_pct: 98.6,
}

export const kpisFixture: KpisResponse = {
  fleet: {
    tool_count: 2,
    events: 2000,
    uptime_pct: 86.7,
    availability_pct: 87.2,
    mtbf_hours: 68.2,
    mttr_hours: 0.93,
    failure_episodes: 24,
    productive_hours: 600,
    unscheduled_down_hours: 24,
    scheduled_down_hours: 8,
    standby_hours: 60,
    engineering_hours: 12,
    wafers: 24000,
    avg_throughput_wph: 50.2,
    avg_yield_pct: 98.6,
    throughput_p50: 43.4,
    throughput_p95: 57.9,
  },
  tools: [
    toolKpi,
    {
      ...toolKpi,
      tool_id: 'METRO-01',
      tool_family: 'METRO',
      uptime_pct: 90.1,
      avg_yield_pct: 99.1,
    },
  ],
  tools_total: 2,
  page: 1,
  page_size: 10,
  sort_by: 'tool_id',
  sort_dir: 'asc',
  throughput_p50: 43.4,
  throughput_p95: 57.9,
  filters: { ...filters, metric: 'throughput_wph' },
}

export const timeseriesFixture: TimeSeriesResponse = {
  metric: 'throughput_wph',
  window: 7,
  sigma: 3,
  series: [
    { date: '2026-01-01', value: 10, rolling_mean: 10, rolling_std: null },
    { date: '2026-01-02', value: 12, rolling_mean: 11, rolling_std: 1.41 },
    { date: '2026-01-03', value: 11, rolling_mean: 11, rolling_std: 1 },
    { date: '2026-01-04', value: 13, rolling_mean: 11.5, rolling_std: 1.29 },
    { date: '2026-01-05', value: 12, rolling_mean: 11.6, rolling_std: 1.14 },
  ],
  center: 11.6,
  std: 1.14,
  ucl: 15.02,
  lcl: 8.18,
  violations: [
    {
      index: 0,
      date: '2026-01-01',
      rule: 'rule_2_eight_same_side',
      description: '8 consecutive points on one side of center',
      value: 10,
    },
  ],
  out_of_control: [{ date: '2026-01-04', value: 13, side: 'above', deviation_sigma: 1.23 }],
  filters: { ...filters, metric: 'throughput_wph' },
}

const box = {
  count: 5,
  min: 1,
  p5: 1.2,
  q1: 3,
  median: 5,
  q3: 7,
  p95: 9.8,
  max: 10,
  mean: 5.2,
  std: 2.1,
  iqr: 4,
  lower_fence: -3,
  upper_fence: 13,
  outliers: [],
}

export const boxplotFixture: BoxplotResponse = {
  metric: 'yield_pct',
  tools: [
    {
      ...box,
      tool_id: 'SCANNER-01',
      tool_family: 'SCANNER',
      outliers: [{ date: '2026-01-04', value: 14.5 }],
    },
    {
      ...box,
      tool_id: 'METRO-01',
      tool_family: 'METRO',
      median: 6,
      outliers: [],
    },
  ],
  fleet: { ...box, outliers: [{ date: '2026-01-04', value: 14.5, tool_id: 'SCANNER-01' }] },
  total_outliers: 1,
  filters,
}

export const paretoFixture: ParetoResponse = {
  rows: [
    {
      fault_code: 'VAC_LOSS',
      fault_category: 'Vacuum',
      severity: 'HIGH',
      count: 100,
      pct_of_total: 50,
      cumulative_pct: 50,
    },
    {
      fault_code: 'TEMP_DRIFT',
      fault_category: 'Thermal',
      severity: 'MEDIUM',
      count: 60,
      pct_of_total: 30,
      cumulative_pct: 80,
    },
    {
      fault_code: 'PARTICLE',
      fault_category: 'Contamination',
      severity: 'MEDIUM',
      count: 40,
      pct_of_total: 20,
      cumulative_pct: 100,
    },
  ],
  codes_for_80: ['VAC_LOSS', 'TEMP_DRIFT'],
  total_events: 200,
  n_codes: 3,
  filters,
}

export const heatmapFixture: HeatmapResponse = {
  tools: ['SCANNER-01', 'METRO-01'],
  shifts: ['A', 'B', 'C'],
  fault_codes: ['VAC_LOSS', 'TEMP_DRIFT'],
  tool_shift: [
    [5, 3, 1],
    [2, 4, 2],
  ],
  tool_fault: [
    [12, 6],
    [8, 4],
  ],
  max_count: 12,
  filters,
}

export const shiftFixture: ShiftDeltaResponse = {
  metric: 'throughput_wph',
  tools: [
    {
      tool_id: 'SCANNER-01',
      shifts: {
        A: { mean: 58.5, std: 0.5, n: 10 },
        B: { mean: 57.3, std: 0.6, n: 10 },
        C: { mean: 53.8, std: 0.4, n: 10 },
      },
      comparisons: [
        {
          tool_id: 'SCANNER-01',
          from_shift: 'B',
          to_shift: 'C',
          from_mean: 57.3,
          to_mean: 53.8,
          abs_delta: -3.5,
          pct_delta: -6.1,
          t_statistic: -12.5,
          p_value: 0.0001,
          significant: true,
        },
      ],
    },
  ],
  strongest: {
    tool_id: 'SCANNER-01',
    from_shift: 'B',
    to_shift: 'C',
    from_mean: 57.3,
    to_mean: 53.8,
    abs_delta: -3.5,
    pct_delta: -6.1,
    t_statistic: -12.5,
    p_value: 0.0001,
    significant: true,
  },
  filters,
}

export const eventsFixture: ToolEventsResponse = {
  tool_id: 'SCANNER-01',
  page: 1,
  page_size: 10,
  total: 25,
  total_pages: 3,
  sort_by: 'ts',
  sort_dir: 'desc',
  rows: [
    {
      event_key: 1,
      ts: '2026-01-10T05:55:00+00:00',
      tool_id: 'SCANNER-01',
      tool_family: 'SCANNER',
      fab_site: 'FAB-A',
      shift: 'C',
      state: 'PRODUCTIVE',
      fault_code: null,
      wafers_processed: 4,
      throughput_wph: 50.1,
      yield_pct: 98.4,
      duration_s: 300,
      recipe_id: 'RCP-LITH-114',
    },
  ],
}

export const reportFixture: ReportResponse = {
  generated_at: '2026-01-11T00:00:00+00:00',
  filters,
  headline: [{ label: 'Uptime', value: '86.7%', detail: 'Fleet productive time.' }],
  summary_sentences: ['The fleet ran at 86.7% uptime.'],
  excursions: [
    {
      rank: 1,
      tool_id: 'SCANNER-01',
      metric: 'throughput_wph',
      severity: 'HIGH',
      headline: 'SCANNER-01 drifted below its center line.',
      detail: 'Eight consecutive days on one side.',
      deviation_sigma: -2.4,
      start_date: '2026-01-02',
      end_date: '2026-01-09',
    },
  ],
  pareto_drivers: paretoFixture.rows,
  shift_deltas: shiftFixture.tools[0].comparisons,
  glossary: [{ term: 'UCL / LCL', definition: 'Control limits at mean ± 3σ.' }],
  date_range: { min_date: '2026-01-01', max_date: '2026-01-10' },
  counts: { events: 2000, tools: 2, days: 10 },
}
