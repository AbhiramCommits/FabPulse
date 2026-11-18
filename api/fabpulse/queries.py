"""Reviewable SQL for FabPulse.

Every heavy aggregation (counts, sums, grouped means, window-based failure
episode detection) lives here so it can be read in one place.  The SQL is
Postgres-first and intentionally avoids dialect-specific functions so the same
statements run on the SQLite fallback.  Distributional math (percentiles,
rolling statistics, t-tests) stays in ``fabpulse.stats`` with pandas/NumPy.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import Engine, bindparam, text

from . import db
from .filters import Filters
from .schema import date_key

#: Metric expressions evaluated inside SQL.  Only these names are accepted.
METRIC_SQL: dict[str, str] = {
    # Mean of the productive intervals' rate.  (A wafer-sum divided by duration
    # quantises at 12 wph because wafers are integer counts per 5-minute event.)
    "throughput_wph": (
        "AVG(CASE WHEN f.state = 'PRODUCTIVE' THEN f.throughput_wph END)"
    ),
    "yield_pct": "AVG(CASE WHEN f.state = 'PRODUCTIVE' THEN f.yield_pct END)",
    "wafers_processed": "SUM(f.wafers_processed)",
    "availability_pct": (
        "100.0 * SUM(CASE WHEN f.state = 'PRODUCTIVE' THEN f.duration_s ELSE 0 END) "
        "/ NULLIF(SUM(f.duration_s), 0)"
    ),
}

DEFAULT_METRIC = "throughput_wph"

#: Whitelisted sortable columns for the event drill-down endpoint.
EVENT_SORT_COLUMNS: dict[str, str] = {
    "ts": "f.ts",
    "state": "f.state",
    "fault_code": "ft.fault_code",
    "throughput_wph": "f.throughput_wph",
    "yield_pct": "f.yield_pct",
    "wafers_processed": "f.wafers_processed",
    "duration_s": "f.duration_s",
    "recipe_id": "f.recipe_id",
}


def metric_expression(metric: str) -> str:
    """Return the SQL expression for a whitelisted metric name.

    Raises:
        ValueError: For an unknown metric (prevents SQL injection).
    """
    try:
        return METRIC_SQL[metric]
    except KeyError as exc:
        allowed = ", ".join(sorted(METRIC_SQL))
        raise ValueError(f"unknown metric {metric!r}; choose one of: {allowed}") from exc


def _where(filters: Filters) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Compile a filter set to a SQL predicate plus bound parameters."""
    clauses = ["1 = 1"]
    params: dict[str, Any] = {}
    expanding: dict[str, Any] = {}
    if filters.from_date is not None:
        clauses.append("d.date_key >= :from_key")
        params["from_key"] = date_key(filters.from_date)
    if filters.to_date is not None:
        clauses.append("d.date_key <= :to_key")
        params["to_key"] = date_key(filters.to_date)
    if filters.tool_ids:
        clauses.append("t.tool_id IN :tool_ids")
        expanding["tool_ids"] = list(filters.tool_ids)
    if filters.tool_family:
        clauses.append("t.tool_family = :tool_family")
        params["tool_family"] = filters.tool_family
    if filters.fab_site:
        clauses.append("t.fab_site = :fab_site")
        params["fab_site"] = filters.fab_site
    if filters.shifts:
        clauses.append("s.shift_code IN :shift_codes")
        expanding["shift_codes"] = list(filters.shifts)
    return " AND ".join(clauses), params, expanding


def _run(
    sql: str,
    filters: Filters | None = None,
    params: dict[str, Any] | None = None,
    engine: Engine | None = None,
) -> pd.DataFrame:
    """Execute *sql* with filter parameters and return a DataFrame."""
    filters = filters or Filters()
    where, bound, expanding = _where(filters)
    statement = text(sql.format(where=where))
    if expanding:
        statement = statement.bindparams(
            *[bindparam(name, expanding=True) for name in expanding]
        )
    merged = {**bound, **(params or {}), **expanding}
    return pd.read_sql_query(statement, engine or db.get_engine(), params=merged)


_FACT_JOINS = """
    FROM fact_tool_event f
    JOIN dim_tool t ON t.tool_key = f.tool_key
    JOIN dim_date d ON d.date_key = f.date_key
    JOIN dim_shift s ON s.shift_key = f.shift_key
"""


def availability_by_tool(
    filters: Filters | None = None, engine: Engine | None = None
) -> pd.DataFrame:
    """Return state-duration sums, wafers and mean yield per tool."""
    sql = f"""
        SELECT
            f.tool_key,
            t.tool_id,
            t.tool_family,
            t.fab_site,
            COUNT(*) AS events,
            COALESCE(SUM(f.duration_s), 0) AS total_s,
            COALESCE(SUM(CASE WHEN f.state = 'PRODUCTIVE' THEN f.duration_s ELSE 0 END), 0) AS productive_s,
            COALESCE(SUM(CASE WHEN f.state = 'STANDBY' THEN f.duration_s ELSE 0 END), 0) AS standby_s,
            COALESCE(SUM(CASE WHEN f.state = 'SCHEDULED_DOWN' THEN f.duration_s ELSE 0 END), 0) AS scheduled_down_s,
            COALESCE(SUM(CASE WHEN f.state = 'UNSCHEDULED_DOWN' THEN f.duration_s ELSE 0 END), 0) AS unscheduled_down_s,
            COALESCE(SUM(CASE WHEN f.state = 'ENGINEERING' THEN f.duration_s ELSE 0 END), 0) AS engineering_s,
            COALESCE(SUM(f.wafers_processed), 0) AS wafers,
            AVG(CASE WHEN f.state = 'PRODUCTIVE' THEN f.throughput_wph END) AS avg_throughput_wph,
            AVG(CASE WHEN f.state = 'PRODUCTIVE' THEN f.yield_pct END) AS avg_yield_pct
        {_FACT_JOINS}
        WHERE {{where}}
        GROUP BY f.tool_key, t.tool_id, t.tool_family, t.fab_site
        ORDER BY t.tool_id
    """
    return _run(sql, filters, engine=engine)


def failure_episodes_by_tool(
    filters: Filters | None = None, engine: Engine | None = None
) -> pd.DataFrame:
    """Count contiguous unscheduled-down episodes per tool.

    A new failure episode starts when an ``UNSCHEDULED_DOWN`` interval is not
    preceded by another ``UNSCHEDULED_DOWN`` interval for the same tool.  The
    window function runs in the database, not in Python.
    """
    sql = f"""
        WITH ordered AS (
            SELECT
                f.tool_key,
                f.state,
                LAG(f.state) OVER (PARTITION BY f.tool_key ORDER BY f.ts, f.event_key) AS prev_state
            {_FACT_JOINS}
            WHERE {{where}}
        )
        SELECT
            o.tool_key,
            COALESCE(SUM(
                CASE
                    WHEN o.state = 'UNSCHEDULED_DOWN'
                         AND (o.prev_state IS NULL OR o.prev_state <> 'UNSCHEDULED_DOWN')
                    THEN 1 ELSE 0
                END
            ), 0) AS failure_episodes
        FROM ordered o
        GROUP BY o.tool_key
    """
    return _run(sql, filters, engine=engine)


def daily_metric_by_tool(
    metric: str = DEFAULT_METRIC,
    filters: Filters | None = None,
    engine: Engine | None = None,
) -> pd.DataFrame:
    """Return one metric value per tool per operational day.

    Returns:
        DataFrame with columns ``tool_id``, ``date_key``, ``date`` and ``value``.
    """
    expression = metric_expression(metric)
    sql = f"""
        SELECT
            t.tool_id,
            f.date_key,
            d."date" AS date,
            {expression} AS value
        {_FACT_JOINS}
        WHERE {{where}}
        GROUP BY t.tool_id, f.date_key, d."date"
        ORDER BY d."date", t.tool_id
    """
    frame = _run(sql, filters, engine=engine)
    if not frame.empty:
        frame["date"] = pd.to_datetime(frame["date"]).dt.date
        frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    return frame


def daily_metric_by_tool_shift(
    metric: str = DEFAULT_METRIC,
    filters: Filters | None = None,
    engine: Engine | None = None,
) -> pd.DataFrame:
    """Return one metric value per tool, shift and operational day."""
    expression = metric_expression(metric)
    sql = f"""
        SELECT
            t.tool_id,
            s.shift_code,
            f.date_key,
            d."date" AS date,
            {expression} AS value
        {_FACT_JOINS}
        WHERE {{where}}
        GROUP BY t.tool_id, s.shift_code, f.date_key, d."date"
        ORDER BY d."date", t.tool_id, s.shift_code
    """
    frame = _run(sql, filters, engine=engine)
    if not frame.empty:
        frame["date"] = pd.to_datetime(frame["date"]).dt.date
        frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    return frame


def fault_counts(
    filters: Filters | None = None, engine: Engine | None = None
) -> pd.DataFrame:
    """Return fault event counts by code, category and severity (descending)."""
    sql = f"""
        SELECT
            ft.fault_code,
            ft.fault_category,
            ft.severity,
            COUNT(*) AS count
        {_FACT_JOINS}
        JOIN dim_fault ft ON ft.fault_key = f.fault_key
        WHERE {{where}}
        GROUP BY ft.fault_code, ft.fault_category, ft.severity
        ORDER BY count DESC, ft.fault_code
    """
    return _run(sql, filters, engine=engine)


def fault_heatmap_rows(
    filters: Filters | None = None, engine: Engine | None = None
) -> pd.DataFrame:
    """Return fault counts grouped by tool, shift and fault code."""
    sql = f"""
        SELECT
            t.tool_id,
            s.shift_code,
            ft.fault_code,
            COUNT(*) AS count
        {_FACT_JOINS}
        JOIN dim_fault ft ON ft.fault_key = f.fault_key
        WHERE {{where}}
        GROUP BY t.tool_id, s.shift_code, ft.fault_code
        ORDER BY t.tool_id, s.shift_code, ft.fault_code
    """
    return _run(sql, filters, engine=engine)


def meta_filters(engine: Engine | None = None) -> dict[str, Any]:
    """Return catalog values used to populate the UI filter drawer."""
    engine = engine or db.get_engine()
    tools = pd.read_sql_query(
        text(
            "SELECT tool_id, tool_family, fab_site, install_date "
            "FROM dim_tool ORDER BY tool_id"
        ),
        engine,
    )
    shifts = pd.read_sql_query(
        text("SELECT shift_code, start_hour, end_hour FROM dim_shift ORDER BY shift_key"),
        engine,
    )
    bounds = pd.read_sql_query(
        text('SELECT MIN("date") AS min_date, MAX("date") AS max_date FROM dim_date'),
        engine,
    )
    faults = pd.read_sql_query(
        text("SELECT fault_code, fault_category, severity FROM dim_fault ORDER BY fault_key"),
        engine,
    )
    min_date = bounds["min_date"].iloc[0] if not bounds.empty else None
    max_date = bounds["max_date"].iloc[0] if not bounds.empty else None
    return {
        "tools": [
            {
                "tool_id": row.tool_id,
                "tool_family": row.tool_family,
                "fab_site": row.fab_site,
                "install_date": (
                    row.install_date.isoformat()
                    if hasattr(row.install_date, "isoformat")
                    else row.install_date
                ),
            }
            for row in tools.itertuples(index=False)
        ],
        "families": sorted(tools["tool_family"].dropna().unique().tolist()),
        "sites": sorted(tools["fab_site"].dropna().unique().tolist()),
        "shifts": shifts.to_dict(orient="records"),
        "fault_codes": faults.to_dict(orient="records"),
        "date_bounds": {
            "min_date": str(min_date)[:10] if min_date is not None else None,
            "max_date": str(max_date)[:10] if max_date is not None else None,
        },
    }


def tool_events_page(
    tool_id: str,
    filters: Filters | None = None,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "ts",
    sort_dir: str = "desc",
    engine: Engine | None = None,
) -> tuple[pd.DataFrame, int]:
    """Return a page of event rows and the total row count for the drill-down.

    Args:
        tool_id: Exact tool id to drill into.
        filters: Additional dashboard filters.
        page: 1-based page number.
        page_size: Rows per page (bounded by the caller).
        sort_by: Whitelisted column key.
        sort_dir: ``asc`` or ``desc``.
        engine: Optional engine override (tests).

    Returns:
        ``(rows, total)`` where rows contain denormalised tool, shift and fault
        labels suitable for an Ant Design table.
    """
    filters = (filters or Filters()).with_overrides(tool_ids=(tool_id,))
    if sort_by not in EVENT_SORT_COLUMNS:
        raise ValueError(f"unknown sort column {sort_by!r}")
    direction = "DESC" if str(sort_dir).lower() != "asc" else "ASC"
    order_column = EVENT_SORT_COLUMNS[sort_by]
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 500))
    offset = (page - 1) * page_size

    count_sql = f"SELECT COUNT(*) AS total {_FACT_JOINS} WHERE {{where}}"
    total = int(_run(count_sql, filters, engine=engine)["total"].iloc[0])

    rows_sql = f"""
        SELECT
            f.event_key,
            f.ts,
            t.tool_id,
            t.tool_family,
            t.fab_site,
            s.shift_code AS shift,
            f.state,
            ft.fault_code,
            f.wafers_processed,
            f.throughput_wph,
            f.yield_pct,
            f.duration_s,
            f.recipe_id
        {_FACT_JOINS}
        LEFT JOIN dim_fault ft ON ft.fault_key = f.fault_key
        WHERE {{where}}
        ORDER BY {order_column} {direction}, f.event_key {direction}
        LIMIT :limit OFFSET :offset
    """
    rows = _run(
        rows_sql,
        filters,
        params={"limit": page_size, "offset": offset},
        engine=engine,
    )
    if not rows.empty:
        rows["ts"] = pd.to_datetime(rows["ts"], utc=True)
    return rows, total


def tool_exists(tool_id: str, engine: Engine | None = None) -> bool:
    """Return ``True`` when *tool_id* exists in ``dim_tool``."""
    engine = engine or db.get_engine()
    frame = pd.read_sql_query(
        text("SELECT 1 AS found FROM dim_tool WHERE tool_id = :tool_id"),
        engine,
        params={"tool_id": tool_id},
    )
    return not frame.empty


def warehouse_counts(engine: Engine | None = None) -> dict[str, int]:
    """Return row counts for every warehouse table (README/health tooling)."""
    engine = engine or db.get_engine()
    counts: dict[str, int] = {}
    for table in ("dim_tool", "dim_date", "dim_shift", "dim_fault", "fact_tool_event"):
        counts[table] = int(
            pd.read_sql_query(text(f"SELECT COUNT(*) AS n FROM {table}"), engine)["n"].iloc[0]
        )
    return counts
