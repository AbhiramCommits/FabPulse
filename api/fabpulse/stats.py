"""Statistical aggregation layer for FabPulse.

Design rule: heavy grouping (counts, sums, grouped means, failure-episode
window functions) happens in SQL (see :mod:`fabpulse.queries`); distributional
work happens here in pandas/NumPy.  Every public function accepts the same
:class:`~fabpulse.filters.Filters` object so the API and the report share one
code path.

No scipy dependency: Welch's t-test is implemented in NumPy and its two-sided
p-value uses a normal approximation (documented on :func:`welch_t_test`).
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from . import queries
from .filters import Filters

#: Metrics surfaced by the dashboard and accepted by every stats function.
SUPPORTED_METRICS = tuple(queries.METRIC_SQL.keys())

#: Confidence threshold used to label a shift delta as significant.
ALPHA = 0.05

#: Western-Electric-style run lengths used by :func:`detect_run_rules`.
RUN_LENGTH_SAME_SIDE = 8
RUN_WINDOW = 5


def coerce_filters(filters: Filters | Mapping[str, Any] | None) -> Filters:
    """Accept a Filters instance, a mapping, or nothing and return Filters."""
    if isinstance(filters, Filters):
        return filters
    return Filters.from_mapping(filters)


def validate_metric(metric: str) -> str:
    """Validate a metric name against the SQL whitelist."""
    if metric not in SUPPORTED_METRICS:
        allowed = ", ".join(SUPPORTED_METRICS)
        raise ValueError(f"unknown metric {metric!r}; choose one of: {allowed}")
    return metric


def _iso(value: Any) -> str | None:
    """Render a date-like value as an ISO date string."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if hasattr(value, "date") and not isinstance(value, date):
        value = value.date()
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def daily_series(
    metric: str = "throughput_wph",
    filters: Filters | Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Return the fleet daily series for *metric*.

    Throughput, yield and availability are averaged across the matching tools;
    wafer counts are summed.  Missing days are not filled so that rolling
    statistics skip gaps rather than inventing zeros.

    Args:
        metric: One of :data:`SUPPORTED_METRICS`.
        filters: Dashboard filter set.

    Returns:
        DataFrame with ``date`` (ISO str) and ``value`` columns sorted by date.
    """
    metric = validate_metric(metric)
    filters = coerce_filters(filters)
    tool_daily = queries.daily_metric_by_tool(metric, filters)
    if tool_daily.empty:
        return pd.DataFrame(columns=["date", "value"])
    aggregation = "sum" if metric == "wafers_processed" else "mean"
    fleet = (
        tool_daily.groupby("date", as_index=False)["value"]
        .agg(aggregation)
        .sort_values("date")
        .reset_index(drop=True)
    )
    fleet["date"] = [_iso(d) for d in fleet["date"]]
    fleet["value"] = pd.to_numeric(fleet["value"], errors="coerce")
    return fleet


def rolling_series(
    metric: str = "throughput_wph",
    window: int = 7,
    filters: Filters | Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Add a rolling mean and rolling standard deviation to the daily series.

    Args:
        metric: One of :data:`SUPPORTED_METRICS`.
        window: Rolling window length in days (1 or greater).
        filters: Dashboard filter set.

    Returns:
        DataFrame with ``date``, ``value``, ``rolling_mean`` and
        ``rolling_std`` columns.
    """
    if int(window) < 1:
        raise ValueError("window must be >= 1")
    frame = daily_series(metric, filters)
    if frame.empty:
        return pd.DataFrame(columns=["date", "value", "rolling_mean", "rolling_std"])
    values = frame["value"]
    frame = frame.copy()
    frame["rolling_mean"] = values.rolling(int(window), min_periods=1).mean()
    frame["rolling_std"] = values.rolling(int(window), min_periods=2).std(ddof=1)
    return frame


def detect_run_rules(
    values: Sequence[float],
    center: float,
    sigma: float,
    dates: Sequence[Any] | None = None,
) -> list[dict[str, Any]]:
    """Detect Western-Electric-style run-rule violations.

    Rules implemented:

    1. Any point beyond mean ± 3σ.
    2. Eight consecutive points on the same side of the center line.
    3. Two of three consecutive points beyond 2σ on the same side.
    4. Four of five consecutive points beyond 1σ on the same side.

    Args:
        values: Ordered time-series values (NaNs are skipped).
        center: Center line (process mean).
        sigma: Process standard deviation.
        dates: Optional parallel labels for the returned violations.

    Returns:
        A list of violation dicts with ``index``, ``date``, ``rule``,
        ``description`` and ``value``.
    """
    clean_indices = [i for i, v in enumerate(values) if v is not None and not pd.isna(v)]
    clean = [float(values[i]) for i in clean_indices]
    labels = [dates[i] if dates is not None else i for i in clean_indices]
    violations: list[dict[str, Any]] = []

    def add(position: int, rule: str, description: str) -> None:
        violations.append(
            {
                "index": clean_indices[position],
                "date": _iso(labels[position]),
                "rule": rule,
                "description": description,
                "value": round(clean[position], 4),
            }
        )

    # Rule 1: beyond three sigma.
    if sigma > 0:
        for position, value in enumerate(clean):
            if abs(value - center) > 3 * sigma:
                side = "above UCL" if value > center else "below LCL"
                add(position, "rule_1_3sigma", f"Point {side} (|z| > 3)")

    # Rule 2: eight consecutive points on one side.
    side_run = 0
    last_side = 0
    for position, value in enumerate(clean):
        side = 1 if value > center else (-1 if value < center else 0)
        if side != 0 and side == last_side:
            side_run += 1
        elif side != 0:
            side_run = 1
        else:
            side_run = 0
        last_side = side
        if side_run == RUN_LENGTH_SAME_SIDE:
            add(position, "rule_2_eight_same_side", "8 consecutive points on one side of center")

    # Rule 3: 2 of 3 beyond two sigma, same side.
    if sigma > 0:
        for end in range(2, len(clean)):
            window = clean[end - 2 : end + 1]
            for side in (1, -1):
                count = sum(1 for v in window if side * (v - center) > 2 * sigma)
                if count >= 2:
                    add(end, "rule_3_two_of_three_2sigma", "2 of 3 points beyond 2σ on one side")
                    break

    # Rule 4: 4 of 5 beyond one sigma, same side.
    if sigma > 0:
        for end in range(RUN_WINDOW - 1, len(clean)):
            window = clean[end - RUN_WINDOW + 1 : end + 1]
            for side in (1, -1):
                count = sum(1 for v in window if side * (v - center) > sigma)
                if count >= 4:
                    add(end, "rule_4_four_of_five_1sigma", "4 of 5 points beyond 1σ on one side")
                    break

    return violations


def compute_control_limits(
    values: Sequence[float],
    sigma: float = 3.0,
    dates: Sequence[Any] | None = None,
    metric: str = "",
) -> dict[str, Any]:
    """Compute a control chart from an in-memory series (pure function).

    Args:
        values: Ordered observations (NaNs are skipped).
        sigma: Control-limit width in standard deviations.
        dates: Optional parallel labels.
        metric: Metric name echoed in the result.

    Returns:
        Dict with ``center``, ``std``, ``ucl``, ``lcl``, ``points``,
        ``out_of_control`` and ``violations``.
    """
    if sigma <= 0:
        raise ValueError("sigma must be positive")
    clean = [float(v) for v in values if v is not None and not pd.isna(v)]
    labels = (
        [d for v, d in zip(values, dates) if v is not None and not pd.isna(v)]
        if dates is not None
        else list(range(len(clean)))
    )
    if not clean:
        return {
            "metric": metric,
            "sigma": sigma,
            "center": None,
            "std": None,
            "ucl": None,
            "lcl": None,
            "n": 0,
            "points": [],
            "out_of_control": [],
            "violations": [],
        }
    center = float(np.mean(clean))
    std = float(np.std(clean, ddof=1)) if len(clean) > 1 else 0.0
    ucl = center + sigma * std
    lcl = center - sigma * std
    points = [
        {"date": _iso(d), "value": round(float(v), 4)} for d, v in zip(labels, clean)
    ]
    out_of_control: list[dict[str, Any]] = []
    if std > 0:
        for label, value in zip(labels, clean):
            deviation = (value - center) / std
            if abs(deviation) > sigma:
                out_of_control.append(
                    {
                        "date": _iso(label),
                        "value": round(float(value), 4),
                        "side": "above" if deviation > 0 else "below",
                        "deviation_sigma": round(deviation, 3),
                    }
                )
    violations = detect_run_rules(clean, center, std, labels)
    return {
        "metric": metric,
        "sigma": sigma,
        "center": round(center, 4),
        "std": round(std, 4),
        "ucl": round(ucl, 4),
        "lcl": round(lcl, 4),
        "n": int(len(clean)),
        "points": points,
        "out_of_control": out_of_control,
        "violations": violations,
    }


def control_limits(
    metric: str = "throughput_wph",
    sigma: float = 3.0,
    filters: Filters | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute a control chart (center line, UCL/LCL, violations) for *metric*.

    Args:
        metric: One of :data:`SUPPORTED_METRICS`.
        sigma: Control-limit width in standard deviations (default 3).
        filters: Dashboard filter set.

    Returns:
        Dict with ``center``, ``std``, ``ucl``, ``lcl``, ``sigma``, ``points``,
        ``out_of_control`` and ``violations``.
    """
    if sigma <= 0:
        raise ValueError("sigma must be positive")
    metric = validate_metric(metric)
    frame = daily_series(metric, filters)
    if frame.empty:
        return {
            "metric": metric,
            "sigma": sigma,
            "center": None,
            "std": None,
            "ucl": None,
            "lcl": None,
            "n": 0,
            "points": [],
            "out_of_control": [],
            "violations": [],
        }
    result = compute_control_limits(
        frame["value"].tolist(), sigma=sigma, dates=frame["date"].tolist(), metric=metric
    )
    return result


def distribution_summary(values: Iterable[float]) -> dict[str, Any]:
    """Summarise a distribution with five-number statistics and IQR fences.

    This is a pure function so the percentile/outlier maths can be tested on a
    known array without touching the warehouse.

    Args:
        values: Numeric observations (NaNs are ignored).

    Returns:
        Dict with count, min, p5, q1, median, q3, p95, max, mean, std, iqr,
        lower_fence and upper_fence.

    Raises:
        ValueError: When no finite observations are supplied.
    """
    array = np.asarray(
        [float(value) for value in values if value is not None and not pd.isna(value)],
        dtype=float,
    )
    if array.size == 0:
        raise ValueError("distribution_summary requires at least one value")
    percentiles = np.percentile(array, [5, 25, 50, 75, 95])
    q1, median, q3 = float(percentiles[1]), float(percentiles[2]), float(percentiles[3])
    iqr = q3 - q1
    return {
        "count": int(array.size),
        "min": round(float(array.min()), 4),
        "p5": round(float(percentiles[0]), 4),
        "q1": round(q1, 4),
        "median": round(median, 4),
        "q3": round(q3, 4),
        "p95": round(float(percentiles[4]), 4),
        "max": round(float(array.max()), 4),
        "mean": round(float(array.mean()), 4),
        "std": round(float(array.std(ddof=1)) if array.size > 1 else 0.0, 4),
        "iqr": round(iqr, 4),
        "lower_fence": round(q1 - 1.5 * iqr, 4),
        "upper_fence": round(q3 + 1.5 * iqr, 4),
    }


def tukey_outliers(
    values: Iterable[float], dates: Sequence[Any] | None = None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return a distribution summary and its Tukey 1.5×IQR outliers."""
    clean = [
        (date_value, float(value))
        for date_value, value in zip(dates or (), values)
        if value is not None and not pd.isna(value)
    ]
    summary = distribution_summary([value for _, value in clean])
    outliers = []
    for date_value, value in clean:
        if value < summary["lower_fence"] or value > summary["upper_fence"]:
            outliers.append({"date": _iso(date_value), "value": round(value, 4)})
    return summary, outliers


def percentiles_outliers(
    metric: str = "throughput_wph",
    filters: Filters | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute per-tool five-number summaries, tails and Tukey outliers.

    Uses tool-day values so each box represents the spread of a tool's daily
    performance.  Fences are ``Q1 - 1.5*IQR`` and ``Q3 + 1.5*IQR``.

    Args:
        metric: One of :data:`SUPPORTED_METRICS`.
        filters: Dashboard filter set.

    Returns:
        Dict with ``tools`` (list of summaries), ``fleet`` summary and
        ``total_outliers``.
    """
    metric = validate_metric(metric)
    filters = coerce_filters(filters)
    frame = queries.daily_metric_by_tool(metric, filters)
    if frame.empty:
        return {"metric": metric, "tools": [], "fleet": None, "total_outliers": 0}

    def summarize(values: np.ndarray, group: pd.DataFrame | None = None) -> dict[str, Any]:
        summary = distribution_summary(values)
        outliers: list[dict[str, Any]] = []
        if group is not None:
            for row in group.itertuples(index=False):
                if pd.isna(row.value):
                    continue
                if row.value < summary["lower_fence"] or row.value > summary["upper_fence"]:
                    entry = {"date": _iso(row.date), "value": round(float(row.value), 4)}
                    if hasattr(row, "tool_id"):
                        entry["tool_id"] = row.tool_id
                    outliers.append(entry)
        return {
            **summary,
            "outliers": sorted(outliers, key=lambda item: abs(item["value"]), reverse=True),
        }

    tools: list[dict[str, Any]] = []
    for tool_id, group in frame.groupby("tool_id", sort=True):
        values = group["value"].dropna().to_numpy(dtype=float)
        if len(values) == 0:
            continue
        summary = summarize(values, group)
        tools.append(
            {
                "tool_id": tool_id,
                "tool_family": group["tool_id"].iloc[0].split("-")[0],
                **summary,
            }
        )
    fleet_values = frame["value"].dropna().to_numpy(dtype=float)
    fleet = summarize(fleet_values, frame) if len(fleet_values) else None
    total_outliers = int(sum(len(t["outliers"]) for t in tools))
    return {"metric": metric, "tools": tools, "fleet": fleet, "total_outliers": total_outliers}


def welch_t_test(sample_a: Iterable[float], sample_b: Iterable[float]) -> dict[str, Any]:
    """Welch's unequal-variance t-test with a normal-approximation p-value.

    scipy is deliberately not a dependency.  The statistic is the standard
    Welch t; the two-sided p-value is ``erfc(|t| / sqrt(2))``, i.e. a normal
    approximation that is accurate for the 60+ observations per shift this
    dataset produces.  For small samples prefer a proper t distribution.

    Args:
        sample_a: First sample (e.g. shift A daily values).
        sample_b: Second sample (e.g. shift B daily values).

    Returns:
        Dict with ``t_statistic``, ``p_value``, ``df`` and ``n_a``/``n_b``.
        Non-computable cases return ``None`` values.
    """
    a = np.asarray([v for v in sample_a if v is not None and not pd.isna(v)], dtype=float)
    b = np.asarray([v for v in sample_b if v is not None and not pd.isna(v)], dtype=float)
    empty = {"t_statistic": None, "p_value": None, "df": None, "n_a": int(len(a)), "n_b": int(len(b))}
    if len(a) < 2 or len(b) < 2:
        return empty
    var_a, var_b = a.var(ddof=1), b.var(ddof=1)
    se = math.sqrt(var_a / len(a) + var_b / len(b))
    if se == 0:
        return {**empty, "t_statistic": 0.0 if a.mean() == b.mean() else None, "p_value": 1.0 if a.mean() == b.mean() else 0.0}
    t_stat = (a.mean() - b.mean()) / se
    numerator = (var_a / len(a) + var_b / len(b)) ** 2
    denominator = (var_a / len(a)) ** 2 / (len(a) - 1) + (var_b / len(b)) ** 2 / (len(b) - 1)
    df = numerator / denominator if denominator > 0 else None
    p_value = math.erfc(abs(t_stat) / math.sqrt(2))
    return {
        "t_statistic": round(float(t_stat), 4),
        "p_value": float(p_value),
        "df": round(float(df), 2) if df is not None else None,
        "n_a": int(len(a)),
        "n_b": int(len(b)),
    }


def shift_over_shift_delta(
    metric: str = "throughput_wph",
    filters: Filters | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare shift A/B/C performance per tool with Welch's t-test.

    Comparisons follow the production handoff order ``A→B``, ``B→C`` and
    ``C→A``.  Each shift's sample is its set of daily means, so the test asks
    whether one shift's daily performance distribution differs from another's.

    Args:
        metric: One of :data:`SUPPORTED_METRICS`.
        filters: Dashboard filter set.

    Returns:
        Dict with ``tools`` (shift means and comparisons), and ``strongest``,
        the most significant comparison across the fleet.
    """
    metric = validate_metric(metric)
    filters = coerce_filters(filters)
    frame = queries.daily_metric_by_tool_shift(metric, filters)
    if frame.empty:
        return {"metric": metric, "tools": [], "strongest": None}

    transitions = (("A", "B"), ("B", "C"), ("C", "A"))
    tools: list[dict[str, Any]] = []
    all_comparisons: list[dict[str, Any]] = []
    for tool_id, group in frame.groupby("tool_id", sort=True):
        samples = {
            code: group.loc[group["shift_code"] == code, "value"].dropna().to_numpy(dtype=float)
            for code in ("A", "B", "C")
        }
        shifts = {
            code: {
                "mean": round(float(values.mean()), 4) if len(values) else None,
                "std": round(float(values.std(ddof=1)), 4) if len(values) > 1 else None,
                "n": int(len(values)),
            }
            for code, values in samples.items()
        }
        comparisons: list[dict[str, Any]] = []
        for from_shift, to_shift in transitions:
            a, b = samples[from_shift], samples[to_shift]
            if len(a) == 0 or len(b) == 0:
                continue
            test = welch_t_test(a, b)
            mean_from, mean_to = float(a.mean()), float(b.mean())
            delta = mean_to - mean_from
            pct = (delta / mean_from * 100.0) if mean_from else None
            entry = {
                "tool_id": tool_id,
                "from_shift": from_shift,
                "to_shift": to_shift,
                "from_mean": round(mean_from, 4),
                "to_mean": round(mean_to, 4),
                "abs_delta": round(delta, 4),
                "pct_delta": round(pct, 3) if pct is not None else None,
                "t_statistic": test["t_statistic"],
                "p_value": test["p_value"],
                "significant": bool(
                    test["p_value"] is not None and test["p_value"] < ALPHA
                ),
            }
            comparisons.append(entry)
            all_comparisons.append(entry)
        tools.append({"tool_id": tool_id, "shifts": shifts, "comparisons": comparisons})

    strongest = None
    if all_comparisons:
        strongest = min(
            all_comparisons,
            key=lambda item: (
                item["p_value"] if item["p_value"] is not None else 1.0,
                -abs(item["pct_delta"] or 0.0),
            ),
        )
    return {"metric": metric, "tools": tools, "strongest": strongest}


def fault_pareto(
    filters: Filters | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the fault Pareto table and its 80% cutoff.

    Args:
        filters: Dashboard filter set.

    Returns:
        Dict with ``rows`` (count, pct_of_total, cumulative_pct),
        ``codes_for_80`` and ``total_events``.
    """
    filters = coerce_filters(filters)
    frame = queries.fault_counts(filters)
    if frame.empty:
        return {"rows": [], "codes_for_80": [], "total_events": 0, "n_codes": 0}
    total = float(frame["count"].sum())
    frame = frame.sort_values(["count", "fault_code"], ascending=[False, True]).reset_index(drop=True)
    frame["pct_of_total"] = frame["count"] / total * 100.0
    frame["cumulative_pct"] = frame["pct_of_total"].cumsum()
    rows = []
    codes_for_80: list[str] = []
    reached = False
    for row in frame.itertuples(index=False):
        if not reached:
            codes_for_80.append(row.fault_code)
            if row.cumulative_pct >= 80.0:
                reached = True
        rows.append(
            {
                "fault_code": row.fault_code,
                "fault_category": row.fault_category,
                "severity": row.severity,
                "count": int(row.count),
                "pct_of_total": round(float(row.pct_of_total), 3),
                "cumulative_pct": round(float(min(row.cumulative_pct, 100.0)), 3),
            }
        )
    return {
        "rows": rows,
        "codes_for_80": codes_for_80,
        "total_events": int(total),
        "n_codes": int(len(rows)),
    }


def fault_heatmap(
    filters: Filters | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return fault-count matrices for tool × shift and tool × fault code.

    Args:
        filters: Dashboard filter set.

    Returns:
        Dict with ``tools``, ``shifts``, ``fault_codes``, ``tool_shift`` (matrix)
        and ``tool_fault`` (matrix), all row-aligned to ``tools``.
    """
    filters = coerce_filters(filters)
    frame = queries.fault_heatmap_rows(filters)
    if frame.empty:
        return {
            "tools": [],
            "shifts": [],
            "fault_codes": [],
            "tool_shift": [],
            "tool_fault": [],
            "max_count": 0,
        }
    tools = sorted(frame["tool_id"].unique().tolist())
    shifts = ["A", "B", "C"]
    fault_order = (
        frame.groupby("fault_code")["count"].sum().sort_values(ascending=False).index.tolist()
    )
    shift_matrix = (
        frame.groupby(["tool_id", "shift_code"])["count"].sum().unstack(fill_value=0)
    )
    fault_matrix = (
        frame.groupby(["tool_id", "fault_code"])["count"].sum().unstack(fill_value=0)
    )
    tool_shift = [
        [int(shift_matrix.loc[tool, shift]) if shift in shift_matrix.columns else 0 for shift in shifts]
        for tool in tools
    ]
    tool_fault = [
        [int(fault_matrix.loc[tool, code]) if code in fault_matrix.columns else 0 for code in fault_order]
        for tool in tools
    ]
    max_count = int(max(max(row) for row in tool_shift + tool_fault))
    return {
        "tools": tools,
        "shifts": shifts,
        "fault_codes": fault_order,
        "tool_shift": tool_shift,
        "tool_fault": tool_fault,
        "max_count": max_count,
    }


def availability_kpis(
    filters: Filters | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute fleet and per-tool availability KPIs.

    Definitions:
        * ``uptime_pct`` = productive time / observed time.
        * ``availability_pct`` = productive / (productive + standby +
          engineering + unscheduled down), i.e. OEE-style availability over
          planned production time (scheduled maintenance excluded).
        * ``mtbf_hours`` = productive hours / unscheduled failure episodes.
        * ``mttr_hours`` = unscheduled down hours / unscheduled failure episodes.

    Args:
        filters: Dashboard filter set.

    Returns:
        Dict with a ``fleet`` summary, a ``tools`` list, throughput percentiles
        and the applied filters.
    """
    filters = coerce_filters(filters)
    availability = queries.availability_by_tool(filters)
    episodes = queries.failure_episodes_by_tool(filters)
    if availability.empty:
        return {
            "fleet": None,
            "tools": [],
            "throughput_p50": None,
            "throughput_p95": None,
            "filters": filters.as_dict(),
        }
    if not episodes.empty:
        availability = availability.merge(episodes, on="tool_key", how="left")
    else:
        availability["failure_episodes"] = 0
    availability["failure_episodes"] = (
        availability["failure_episodes"].fillna(0).astype(int)
    )

    tools: list[dict[str, Any]] = []
    for row in availability.itertuples(index=False):
        productive = float(row.productive_s or 0)
        unscheduled = float(row.unscheduled_down_s or 0)
        scheduled = float(row.scheduled_down_s or 0)
        standby = float(row.standby_s or 0)
        engineering = float(row.engineering_s or 0)
        total = float(row.total_s or 0)
        failures = int(row.failure_episodes)
        planned = max(productive + standby + engineering + unscheduled, 1e-9)
        tools.append(
            {
                "tool_id": row.tool_id,
                "tool_family": row.tool_family,
                "fab_site": row.fab_site,
                "events": int(row.events),
                "uptime_pct": round(productive / total * 100.0, 3) if total else None,
                "availability_pct": round(productive / planned * 100.0, 3),
                "mtbf_hours": round(productive / 3600.0 / failures, 3) if failures else None,
                "mttr_hours": round(unscheduled / 3600.0 / failures, 3) if failures else None,
                "failure_episodes": failures,
                "productive_hours": round(productive / 3600.0, 3),
                "unscheduled_down_hours": round(unscheduled / 3600.0, 3),
                "scheduled_down_hours": round(scheduled / 3600.0, 3),
                "standby_hours": round(standby / 3600.0, 3),
                "engineering_hours": round(engineering / 3600.0, 3),
                "wafers": int(row.wafers),
                "avg_throughput_wph": round(float(row.avg_throughput_wph), 3)
                if row.avg_throughput_wph is not None and not pd.isna(row.avg_throughput_wph)
                else None,
                "avg_yield_pct": round(float(row.avg_yield_pct), 3)
                if row.avg_yield_pct is not None and not pd.isna(row.avg_yield_pct)
                else None,
            }
        )

    total_s = float(availability["total_s"].sum())
    productive_s = float(availability["productive_s"].sum())
    unscheduled_s = float(availability["unscheduled_down_s"].sum())
    scheduled_s = float(availability["scheduled_down_s"].sum())
    standby_s = float(availability["standby_s"].sum())
    engineering_s = float(availability["engineering_s"].sum())
    failures = int(availability["failure_episodes"].sum())
    planned_s = max(productive_s + standby_s + engineering_s + unscheduled_s, 1e-9)
    wafers = int(availability["wafers"].sum())
    yield_weights = availability["avg_yield_pct"].notna() & (availability["productive_s"] > 0)
    weighted_yield = (
        float(
            (availability.loc[yield_weights, "avg_yield_pct"] * availability.loc[yield_weights, "productive_s"]).sum()
            / availability.loc[yield_weights, "productive_s"].sum()
        )
        if yield_weights.any()
        else None
    )
    daily = queries.daily_metric_by_tool("throughput_wph", filters)
    p50 = p95 = None
    if not daily.empty:
        values = daily["value"].dropna()
        if not values.empty:
            p50 = round(float(np.percentile(values, 50)), 3)
            p95 = round(float(np.percentile(values, 95)), 3)

    fleet = {
        "tool_count": int(availability["tool_id"].nunique()),
        "events": int(availability["events"].sum()),
        "uptime_pct": round(productive_s / total_s * 100.0, 3) if total_s else None,
        "availability_pct": round(productive_s / planned_s * 100.0, 3),
        "mtbf_hours": round(productive_s / 3600.0 / failures, 3) if failures else None,
        "mttr_hours": round(unscheduled_s / 3600.0 / failures, 3) if failures else None,
        "failure_episodes": failures,
        "productive_hours": round(productive_s / 3600.0, 3),
        "unscheduled_down_hours": round(unscheduled_s / 3600.0, 3),
        "scheduled_down_hours": round(scheduled_s / 3600.0, 3),
        "standby_hours": round(standby_s / 3600.0, 3),
        "engineering_hours": round(engineering_s / 3600.0, 3),
        "wafers": wafers,
        "avg_throughput_wph": round(float(availability["avg_throughput_wph"].mean()), 3)
        if not availability.empty
        else None,
        "avg_yield_pct": round(weighted_yield, 3) if weighted_yield is not None else None,
        "throughput_p50": p50,
        "throughput_p95": p95,
    }
    return {
        "fleet": fleet,
        "tools": tools,
        "throughput_p50": p50,
        "throughput_p95": p95,
        "filters": filters.as_dict(),
    }


def date_bounds(filters: Filters | Mapping[str, Any] | None = None) -> dict[str, str | None]:
    """Return the observed operational-date bounds for the current filters."""
    filters = coerce_filters(filters)
    frame = queries.daily_metric_by_tool("throughput_wph", filters)
    if frame.empty:
        return {"min_date": None, "max_date": None}
    return {
        "min_date": _iso(frame["date"].min()),
        "max_date": _iso(frame["date"].max()),
    }
