"""FabPulse FastAPI application.

All endpoints share one :class:`FilterParams` query-parameter dependency so the
dashboard, the report and the exporter analyse exactly the same slice.  SQL and
statistics live in :mod:`fabpulse.queries` and :mod:`fabpulse.stats`; this
module only validates input, shapes output and maps errors to HTTP statuses.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Annotated

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from . import __version__, config, db, queries, report, stats
from .filters import Filters
from .models import (
    BoxplotResponse,
    DateBounds,
    EventRow,
    FilterEcho,
    FilterOptionsResponse,
    HeatmapResponse,
    HealthResponse,
    KpisResponse,
    ParetoResponse,
    ReportResponse,
    ShiftDeltaResponse,
    TimeSeriesPoint,
    TimeSeriesResponse,
    ToolEventsResponse,
)
from .queries import DEFAULT_METRIC, EVENT_SORT_COLUMNS

logger = logging.getLogger(__name__)

CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "FABPULSE_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

app = FastAPI(
    title="FabPulse API",
    version=__version__,
    description=(
        "Semiconductor equipment telemetry analytics: star-schema warehouse, "
        "SPC statistics and engineer-ready summaries."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)


class FilterParams(BaseModel):
    """Shared filter query parameters accepted by every analytical endpoint."""

    from_date: date | None = None
    to_date: date | None = None
    tool_ids: list[str] = Field(default_factory=list)
    tool_family: str | None = None
    fab_site: str | None = None
    shifts: list[str] = Field(default_factory=list)
    metric: str = DEFAULT_METRIC

    def to_filters(self) -> Filters:
        """Convert to the analytics-layer filter object."""
        return Filters.from_mapping(self.model_dump())

    def echo(self) -> FilterEcho:
        """Return the normalised filter echo used in responses."""
        return FilterEcho(**self.to_filters().as_dict())


def _split_values(values: list[str] | None) -> list[str]:
    """Accept repeated params and comma-separated values for tool/shift lists."""
    if not values:
        return []
    return [part.strip() for value in values for part in str(value).split(",") if part.strip()]


def get_filter_params(
    from_date: Annotated[date | None, Query(description="Inclusive operational start date")] = None,
    to_date: Annotated[date | None, Query(description="Inclusive operational end date")] = None,
    tool_ids: Annotated[list[str] | None, Query(description="Tool id (repeatable)")] = None,
    tool_family: Annotated[str | None, Query(description="SCANNER, TRACK or METRO")] = None,
    fab_site: Annotated[str | None, Query(description="FAB-A or FAB-B")] = None,
    shifts: Annotated[list[str] | None, Query(description="Shift code (repeatable)")] = None,
    metric: Annotated[str, Query(description="Metric for series and box plots")] = DEFAULT_METRIC,
) -> FilterParams:
    """Validate and normalise the shared dashboard filters (400 on bad input)."""
    params = FilterParams(
        from_date=from_date,
        to_date=to_date,
        tool_ids=_split_values(tool_ids),
        tool_family=tool_family.strip().upper() if tool_family else None,
        fab_site=fab_site.strip().upper() if fab_site else None,
        shifts=[value.upper() for value in _split_values(shifts)],
        metric=metric,
    )
    try:
        filters = params.to_filters()
        filters.validate()
        stats.validate_metric(params.metric)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return params


FilterDep = Annotated[FilterParams, Depends(get_filter_params)]


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request, exc: RequestValidationError) -> JSONResponse:
    """Return 400 (not 422) for malformed query parameters, per the API contract."""
    return JSONResponse(status_code=400, content={"detail": "Invalid request parameters", "errors": exc.errors()})


@app.exception_handler(ValueError)
async def value_error_handler(_request, exc: ValueError) -> JSONResponse:
    """Map analytics-layer validation errors to 400 Bad Request."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(_request, exc: SQLAlchemyError) -> JSONResponse:
    """Return 503 when the warehouse cannot be reached or queried."""
    logger.exception("warehouse query failed", exc_info=exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Warehouse unavailable; run `make ingest` and retry."},
    )


@app.get("/api/health", response_model=HealthResponse, tags=["system"])
def api_health() -> HealthResponse:
    """Report service health, active database backend and warehouse size."""
    rows: int | None = None
    try:
        rows = queries.warehouse_counts().get("fact_tool_event")
    except Exception:  # pragma: no cover - depends on warehouse state
        rows = None
    return HealthResponse(
        status="ok" if db.ping() else "degraded",
        service="FabPulse API",
        version=__version__,
        database=config.database_label(str(db.get_engine().url)),
        warehouse_rows=rows,
    )


@app.get("/api/meta/filters", response_model=FilterOptionsResponse, tags=["meta"])
def filter_options() -> FilterOptionsResponse:
    """Return tools, families, sites, shifts, faults and the observed date bounds."""
    meta = queries.meta_filters()
    return FilterOptionsResponse(
        tools=meta["tools"],
        families=meta["families"],
        sites=meta["sites"],
        shifts=meta["shifts"],
        fault_codes=meta["fault_codes"],
        date_bounds=DateBounds(**meta["date_bounds"]),
    )


KPI_SORT_COLUMNS = {
    "tool_id",
    "tool_family",
    "fab_site",
    "uptime_pct",
    "availability_pct",
    "mtbf_hours",
    "mttr_hours",
    "failure_episodes",
    "avg_throughput_wph",
    "avg_yield_pct",
    "productive_hours",
    "wafers",
}


@app.get("/api/kpis", response_model=KpisResponse, tags=["analytics"])
def kpis(
    params: FilterDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
    sort_by: Annotated[str, Query()] = "tool_id",
    sort_dir: Annotated[str, Query(pattern="^(asc|desc)$")] = "asc",
) -> KpisResponse:
    """Return fleet KPIs and a server-paged, server-sorted slice of tool KPIs."""
    if sort_by not in KPI_SORT_COLUMNS:
        raise HTTPException(
            status_code=400,
            detail=f"sort_by must be one of: {', '.join(sorted(KPI_SORT_COLUMNS))}",
        )
    data = stats.availability_kpis(params.to_filters())
    tools = list(data["tools"])

    def sort_value(tool: dict) -> object:
        value = tool.get(sort_by)
        if isinstance(value, str):
            return value.lower()
        if value is None:
            return float("inf") if sort_dir == "asc" else float("-inf")
        return float(value)

    tools.sort(key=sort_value, reverse=sort_dir == "desc")
    total = len(tools)
    start = (page - 1) * page_size
    return KpisResponse(
        fleet=data["fleet"],
        tools=tools[start : start + page_size],
        tools_total=total,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        throughput_p50=data["throughput_p50"],
        throughput_p95=data["throughput_p95"],
        filters=params.echo(),
    )


@app.get("/api/timeseries", response_model=TimeSeriesResponse, tags=["analytics"])
def timeseries(
    params: FilterDep,
    window: Annotated[int, Query(ge=1, le=365)] = 7,
    sigma: Annotated[float, Query(gt=0, le=6)] = 3.0,
) -> TimeSeriesResponse:
    """Return the daily metric series with rolling stats and control limits."""
    filters = params.to_filters()
    frame = stats.rolling_series(params.metric, window, filters)
    limits = stats.control_limits(params.metric, sigma, filters)
    series: list[TimeSeriesPoint] = []
    for row in frame.itertuples(index=False):
        series.append(
            TimeSeriesPoint(
                date=str(row.date),
                value=None if pd.isna(row.value) else round(float(row.value), 4),
                rolling_mean=None if pd.isna(row.rolling_mean) else round(float(row.rolling_mean), 4),
                rolling_std=None if pd.isna(row.rolling_std) else round(float(row.rolling_std), 4),
            )
        )
    return TimeSeriesResponse(
        metric=params.metric,
        window=window,
        sigma=sigma,
        series=series,
        center=limits["center"],
        std=limits["std"],
        ucl=limits["ucl"],
        lcl=limits["lcl"],
        violations=limits["violations"],
        out_of_control=limits["out_of_control"],
        filters=params.echo(),
    )


@app.get("/api/boxplot", response_model=BoxplotResponse, tags=["analytics"])
def boxplot(params: FilterDep) -> BoxplotResponse:
    """Return per-tool five-number summaries, IQR fences and Tukey outliers."""
    data = stats.percentiles_outliers(params.metric, params.to_filters())
    return BoxplotResponse(
        metric=data["metric"],
        tools=data["tools"],
        fleet=data["fleet"],
        total_outliers=data["total_outliers"],
        filters=params.echo(),
    )


@app.get("/api/pareto", response_model=ParetoResponse, tags=["analytics"])
def pareto(params: FilterDep) -> ParetoResponse:
    """Return the fault Pareto table with the 80% cutoff codes."""
    data = stats.fault_pareto(params.to_filters())
    return ParetoResponse(**data, filters=params.echo())


@app.get("/api/heatmap", response_model=HeatmapResponse, tags=["analytics"])
def heatmap(params: FilterDep) -> HeatmapResponse:
    """Return fault-count matrices for tool × shift and tool × fault code."""
    data = stats.fault_heatmap(params.to_filters())
    return HeatmapResponse(**data, filters=params.echo())


@app.get("/api/shifts/delta", response_model=ShiftDeltaResponse, tags=["analytics"])
def shift_delta(params: FilterDep) -> ShiftDeltaResponse:
    """Return per-tool shift means and Welch-tested handoff comparisons."""
    data = stats.shift_over_shift_delta(params.metric, params.to_filters())
    return ShiftDeltaResponse(**data, filters=params.echo())


@app.get(
    "/api/tools/{tool_id}/events",
    response_model=ToolEventsResponse,
    tags=["drilldown"],
)
def tool_events(
    tool_id: str,
    params: FilterDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 25,
    sort_by: Annotated[str, Query()] = "ts",
    sort_dir: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> ToolEventsResponse:
    """Return a server-paginated, server-sorted event timeline for one tool."""
    if sort_by not in EVENT_SORT_COLUMNS:
        raise HTTPException(
            status_code=400,
            detail=f"sort_by must be one of: {', '.join(sorted(EVENT_SORT_COLUMNS))}",
        )
    if not queries.tool_exists(tool_id):
        raise HTTPException(status_code=404, detail=f"unknown tool: {tool_id}")
    rows, total = queries.tool_events_page(
        tool_id,
        params.to_filters(),
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    records: list[EventRow] = []
    for row in rows.itertuples(index=False):
        timestamp = row.ts.isoformat() if hasattr(row.ts, "isoformat") else str(row.ts)
        records.append(
            EventRow(
                event_key=int(row.event_key),
                ts=timestamp,
                tool_id=str(row.tool_id),
                tool_family=str(row.tool_family),
                fab_site=str(row.fab_site),
                shift=str(row.shift),
                state=str(row.state),
                fault_code=None if pd.isna(row.fault_code) else str(row.fault_code),
                wafers_processed=int(row.wafers_processed),
                throughput_wph=round(float(row.throughput_wph), 3),
                yield_pct=None if pd.isna(row.yield_pct) else round(float(row.yield_pct), 3),
                duration_s=int(row.duration_s),
                recipe_id=None if pd.isna(row.recipe_id) else str(row.recipe_id),
            )
        )
    total_pages = max(1, (total + page_size - 1) // page_size)
    return ToolEventsResponse(
        tool_id=tool_id,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        sort_by=sort_by,
        sort_dir=sort_dir,
        rows=records,
    )


@app.get("/api/report/summary", response_model=ReportResponse, tags=["report"])
def report_summary(params: FilterDep) -> ReportResponse:
    """Return the plain-language engineer summary for the current filters."""
    data = report.build_summary(params.to_filters(), metric=params.metric)
    return ReportResponse(**data)
