"""Pydantic v2 request/response contracts for the FabPulse API.

The hand-written TypeScript interfaces in ``web/src/api/types.ts`` mirror these
models; ``scripts/openapi_snapshot.py`` writes ``api/openapi.json`` so the two
can be compared in review.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

MetricName = Literal[
    "throughput_wph", "yield_pct", "wafers_processed", "availability_pct"
]


class HealthResponse(BaseModel):
    """Service and warehouse health."""

    status: str
    service: str
    version: str
    database: str
    warehouse_rows: int | None = None


class ToolMeta(BaseModel):
    """Tool catalog entry."""

    tool_id: str
    tool_family: str
    fab_site: str
    install_date: str | None = None


class ShiftMeta(BaseModel):
    """Shift catalog entry."""

    shift_code: str
    start_hour: int
    end_hour: int


class FaultMeta(BaseModel):
    """Fault vocabulary entry."""

    fault_code: str
    fault_category: str
    severity: str


class DateBounds(BaseModel):
    """Observed operational-date window."""

    min_date: str | None = None
    max_date: str | None = None


class FilterOptionsResponse(BaseModel):
    """Everything the filter drawer needs to populate itself."""

    tools: list[ToolMeta]
    families: list[str]
    sites: list[str]
    shifts: list[ShiftMeta]
    fault_codes: list[FaultMeta]
    date_bounds: DateBounds


class FilterEcho(BaseModel):
    """Normalised filters echoed back with analytical responses."""

    from_date: str | None = None
    to_date: str | None = None
    tool_ids: list[str] = Field(default_factory=list)
    tool_family: str | None = None
    fab_site: str | None = None
    shifts: list[str] = Field(default_factory=list)


class FleetKpi(BaseModel):
    """Fleet-level availability and throughput KPIs."""

    tool_count: int
    events: int
    uptime_pct: float | None
    availability_pct: float | None
    mtbf_hours: float | None
    mttr_hours: float | None
    failure_episodes: int
    productive_hours: float
    unscheduled_down_hours: float
    scheduled_down_hours: float
    standby_hours: float
    engineering_hours: float
    wafers: int
    avg_throughput_wph: float | None
    avg_yield_pct: float | None
    throughput_p50: float | None
    throughput_p95: float | None


class ToolKpi(BaseModel):
    """Per-tool KPI card values."""

    tool_id: str
    tool_family: str
    fab_site: str
    events: int
    uptime_pct: float | None
    availability_pct: float | None
    mtbf_hours: float | None
    mttr_hours: float | None
    failure_episodes: int
    productive_hours: float
    unscheduled_down_hours: float
    scheduled_down_hours: float
    standby_hours: float
    engineering_hours: float
    wafers: int
    avg_throughput_wph: float | None
    avg_yield_pct: float | None


class KpisResponse(BaseModel):
    """Fleet and per-tool KPIs for the current filters.

    ``tools`` is one server-side page; ``tools_total`` powers Ant Design's
    pagination control without shipping the whole fleet to the browser.
    """

    fleet: FleetKpi | None
    tools: list[ToolKpi]
    tools_total: int = 0
    page: int = 1
    page_size: int = 10
    sort_by: str = "tool_id"
    sort_dir: str = "asc"
    throughput_p50: float | None = None
    throughput_p95: float | None = None
    filters: FilterEcho


class TimeSeriesPoint(BaseModel):
    """One day of the metric series plus rolling statistics."""

    date: str
    value: float | None = None
    rolling_mean: float | None = None
    rolling_std: float | None = None


class OutOfControlPoint(BaseModel):
    """A point outside the 3σ control limits."""

    date: str
    value: float
    side: str
    deviation_sigma: float


class RunRuleViolation(BaseModel):
    """A Western-Electric-style run-rule violation."""

    index: int
    date: str | None
    rule: str
    description: str
    value: float


class TimeSeriesResponse(BaseModel):
    """Daily series with rolling stats, control limits and violations."""

    metric: str
    window: int
    sigma: float
    series: list[TimeSeriesPoint]
    center: float | None
    std: float | None
    ucl: float | None
    lcl: float | None
    violations: list[RunRuleViolation]
    out_of_control: list[OutOfControlPoint]
    filters: FilterEcho


class BoxplotOutlier(BaseModel):
    """A single Tukey outlier with its observation date."""

    date: str
    value: float
    tool_id: str | None = None


class BoxSummary(BaseModel):
    """Five-number summary plus tails, IQR fences and outliers."""

    count: int
    min: float
    p5: float
    q1: float
    median: float
    q3: float
    p95: float
    max: float
    mean: float
    std: float
    iqr: float
    lower_fence: float
    upper_fence: float
    outliers: list[BoxplotOutlier]


class ToolBoxSummary(BoxSummary):
    """Per-tool box plot summary."""

    tool_id: str
    tool_family: str


class BoxplotResponse(BaseModel):
    """Per-tool distributions for the excursion box plot."""

    metric: str
    tools: list[ToolBoxSummary]
    fleet: BoxSummary | None = None
    total_outliers: int
    filters: FilterEcho


class ParetoRow(BaseModel):
    """One fault code in the Pareto table."""

    fault_code: str
    fault_category: str
    severity: str
    count: int
    pct_of_total: float
    cumulative_pct: float


class ParetoResponse(BaseModel):
    """Fault Pareto with the 80% cutoff codes."""

    rows: list[ParetoRow]
    codes_for_80: list[str]
    total_events: int
    n_codes: int
    filters: FilterEcho


class HeatmapResponse(BaseModel):
    """Fault counts by tool × shift and tool × fault code."""

    tools: list[str]
    shifts: list[str]
    fault_codes: list[str]
    tool_shift: list[list[int]]
    tool_fault: list[list[int]]
    max_count: int
    filters: FilterEcho


class EventRow(BaseModel):
    """One event row in the drill-down table."""

    event_key: int
    ts: str
    tool_id: str
    tool_family: str
    fab_site: str
    shift: str
    state: str
    fault_code: str | None = None
    wafers_processed: int
    throughput_wph: float
    yield_pct: float | None = None
    duration_s: int
    recipe_id: str | None = None


class ToolEventsResponse(BaseModel):
    """Server-paginated event timeline for one tool."""

    tool_id: str
    page: int
    page_size: int
    total: int
    total_pages: int
    sort_by: str
    sort_dir: str
    rows: list[EventRow]


class ShiftSummary(BaseModel):
    """Mean, standard deviation and sample size for one shift."""

    mean: float | None
    std: float | None
    n: int


class ShiftComparison(BaseModel):
    """One handoff comparison with a Welch t-test result."""

    tool_id: str
    from_shift: str
    to_shift: str
    from_mean: float
    to_mean: float
    abs_delta: float
    pct_delta: float | None
    t_statistic: float | None
    p_value: float | None
    significant: bool


class ToolShiftDelta(BaseModel):
    """Shift means and handoff comparisons for one tool."""

    tool_id: str
    shifts: dict[str, ShiftSummary]
    comparisons: list[ShiftComparison]


class ShiftDeltaResponse(BaseModel):
    """Shift-over-shift analysis for the current filters."""

    metric: str
    tools: list[ToolShiftDelta]
    strongest: ShiftComparison | None
    filters: FilterEcho


class GlossaryEntry(BaseModel):
    """A plain-language metric definition."""

    term: str
    definition: str


class HeadlineKpi(BaseModel):
    """One plain-language headline number."""

    label: str
    value: str
    detail: str


class Excursion(BaseModel):
    """A ranked, plain-language excursion finding."""

    rank: int
    tool_id: str
    metric: str
    severity: str
    headline: str
    detail: str
    deviation_sigma: float | None = None
    start_date: str | None = None
    end_date: str | None = None


class ReportResponse(BaseModel):
    """Structured engineer summary consumed by ``/report`` and the exporter."""

    generated_at: str
    filters: FilterEcho
    headline: list[HeadlineKpi]
    summary_sentences: list[str]
    excursions: list[Excursion]
    pareto_drivers: list[ParetoRow]
    shift_deltas: list[ShiftComparison]
    glossary: list[GlossaryEntry]
    date_range: DateBounds
    counts: dict[str, Any]
