/**
 * Hand-written TypeScript mirrors of the Pydantic models in
 * `api/fabpulse/models.py`. The OpenAPI snapshot at `api/openapi.json` is the
 * machine-readable reference; these interfaces add ergonomic names for the UI.
 */

export type Metric = 'throughput_wph' | 'yield_pct' | 'wafers_processed' | 'availability_pct'

export type ShiftCode = 'A' | 'B' | 'C'

export interface FilterState {
  from_date: string | null
  to_date: string | null
  tool_ids: string[]
  tool_family: string | null
  fab_site: string | null
  shifts: ShiftCode[]
  metric: Metric
}

export interface FilterEcho {
  from_date: string | null
  to_date: string | null
  tool_ids: string[]
  tool_family: string | null
  fab_site: string | null
  shifts: string[]
  metric?: Metric | null
}

export interface HealthResponse {
  status: string
  service: string
  version: string
  database: string
  warehouse_rows: number | null
}

export interface ToolMeta {
  tool_id: string
  tool_family: string
  fab_site: string
  install_date: string | null
}

export interface ShiftMeta {
  shift_code: string
  start_hour: number
  end_hour: number
}

export interface FaultMeta {
  fault_code: string
  fault_category: string
  severity: string
}

export interface DateBounds {
  min_date: string | null
  max_date: string | null
}

export interface FilterOptionsResponse {
  tools: ToolMeta[]
  families: string[]
  sites: string[]
  shifts: ShiftMeta[]
  fault_codes: FaultMeta[]
  date_bounds: DateBounds
}

export interface FleetKpi {
  tool_count: number
  events: number
  uptime_pct: number | null
  availability_pct: number | null
  mtbf_hours: number | null
  mttr_hours: number | null
  failure_episodes: number
  productive_hours: number
  unscheduled_down_hours: number
  scheduled_down_hours: number
  standby_hours: number
  engineering_hours: number
  wafers: number
  avg_throughput_wph: number | null
  avg_yield_pct: number | null
  throughput_p50: number | null
  throughput_p95: number | null
}

export interface ToolKpi {
  tool_id: string
  tool_family: string
  fab_site: string
  events: number
  uptime_pct: number | null
  availability_pct: number | null
  mtbf_hours: number | null
  mttr_hours: number | null
  failure_episodes: number
  productive_hours: number
  unscheduled_down_hours: number
  scheduled_down_hours: number
  standby_hours: number
  engineering_hours: number
  wafers: number
  avg_throughput_wph: number | null
  avg_yield_pct: number | null
}

export interface KpisResponse {
  fleet: FleetKpi | null
  tools: ToolKpi[]
  tools_total: number
  page: number
  page_size: number
  sort_by: string
  sort_dir: 'asc' | 'desc'
  throughput_p50: number | null
  throughput_p95: number | null
  filters: FilterEcho
}

export interface TimeSeriesPoint {
  date: string
  value: number | null
  rolling_mean: number | null
  rolling_std: number | null
}

export interface OutOfControlPoint {
  date: string
  value: number
  side: 'above' | 'below'
  deviation_sigma: number
}

export interface RunRuleViolation {
  index: number
  date: string | null
  rule: string
  description: string
  value: number
}

export interface TimeSeriesResponse {
  metric: Metric
  window: number
  sigma: number
  series: TimeSeriesPoint[]
  center: number | null
  std: number | null
  ucl: number | null
  lcl: number | null
  violations: RunRuleViolation[]
  out_of_control: OutOfControlPoint[]
  filters: FilterEcho
}

export interface BoxplotOutlier {
  date: string
  value: number
  tool_id?: string | null
}

export interface BoxSummary {
  count: number
  min: number
  p5: number
  q1: number
  median: number
  q3: number
  p95: number
  max: number
  mean: number
  std: number
  iqr: number
  lower_fence: number
  upper_fence: number
  outliers: BoxplotOutlier[]
}

export interface ToolBoxSummary extends BoxSummary {
  tool_id: string
  tool_family: string
}

export interface BoxplotResponse {
  metric: Metric
  tools: ToolBoxSummary[]
  fleet: BoxSummary | null
  total_outliers: number
  filters: FilterEcho
}

export interface ParetoRow {
  fault_code: string
  fault_category: string
  severity: string
  count: number
  pct_of_total: number
  cumulative_pct: number
}

export interface ParetoResponse {
  rows: ParetoRow[]
  codes_for_80: string[]
  total_events: number
  n_codes: number
  filters: FilterEcho
}

export interface HeatmapResponse {
  tools: string[]
  shifts: string[]
  fault_codes: string[]
  tool_shift: number[][]
  tool_fault: number[][]
  max_count: number
  filters: FilterEcho
}

export interface EventRow {
  event_key: number
  ts: string
  tool_id: string
  tool_family: string
  fab_site: string
  shift: string
  state: string
  fault_code: string | null
  wafers_processed: number
  throughput_wph: number
  yield_pct: number | null
  duration_s: number
  recipe_id: string | null
}

export interface ToolEventsResponse {
  tool_id: string
  page: number
  page_size: number
  total: number
  total_pages: number
  sort_by: string
  sort_dir: 'asc' | 'desc'
  rows: EventRow[]
}

export interface ShiftSummary {
  mean: number | null
  std: number | null
  n: number
}

export interface ShiftComparison {
  tool_id: string
  from_shift: string
  to_shift: string
  from_mean: number
  to_mean: number
  abs_delta: number
  pct_delta: number | null
  t_statistic: number | null
  p_value: number | null
  significant: boolean
}

export interface ToolShiftDelta {
  tool_id: string
  shifts: Record<string, ShiftSummary>
  comparisons: ShiftComparison[]
}

export interface ShiftDeltaResponse {
  metric: Metric
  tools: ToolShiftDelta[]
  strongest: ShiftComparison | null
  filters: FilterEcho
}

export interface GlossaryEntry {
  term: string
  definition: string
}

export interface HeadlineKpi {
  label: string
  value: string
  detail: string
}

export interface Excursion {
  rank: number
  tool_id: string
  metric: Metric
  severity: string
  headline: string
  detail: string
  deviation_sigma: number | null
  start_date: string | null
  end_date: string | null
}

export interface ReportResponse {
  generated_at: string
  filters: FilterEcho
  headline: HeadlineKpi[]
  summary_sentences: string[]
  excursions: Excursion[]
  pareto_drivers: ParetoRow[]
  shift_deltas: ShiftComparison[]
  glossary: GlossaryEntry[]
  date_range: DateBounds
  counts: Record<string, number>
}
