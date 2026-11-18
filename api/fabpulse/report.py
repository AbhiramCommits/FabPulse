"""Plain-language engineer summary for the current filter set.

The report turns the statistical layer into sentences a non-technical
stakeholder can read, ranks excursions, names the Pareto fault drivers, calls
out significant shift handoffs and ships a glossary.  It is shared by the
``/api/report/summary`` endpoint and ``scripts/export_report.py`` so browser
and file exports never drift apart.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from . import queries, stats
from .filters import Filters

GLOSSARY: tuple[dict[str, str], ...] = (
    {
        "term": "UCL / LCL",
        "definition": (
            "Upper and lower control limits, drawn at the process mean ± 3 standard "
            "deviations; a point outside them is unlikely under stable random variation."
        ),
    },
    {
        "term": "MTBF",
        "definition": (
            "Mean time between failures: productive hours divided by the number of "
            "unscheduled-down episodes."
        ),
    },
    {
        "term": "MTTR",
        "definition": (
            "Mean time to repair: total unscheduled-down hours divided by the number "
            "of unscheduled-down episodes."
        ),
    },
    {
        "term": "IQR",
        "definition": (
            "Interquartile range, the distance between the 25th and 75th percentiles; "
            "Tukey outliers lie beyond 1.5×IQR from the box."
        ),
    },
    {
        "term": "p-value",
        "definition": (
            "The probability of seeing a difference at least this large if nothing "
            "real changed; below 0.05 is conventionally called significant."
        ),
    },
    {
        "term": "Availability (OEE)",
        "definition": (
            "Productive time divided by planned production time, excluding scheduled "
            "maintenance but including standby, engineering and unplanned downtime."
        ),
    },
    {
        "term": "Rolling mean",
        "definition": (
            "The average of a metric over a trailing window of days, used to separate "
            "signal from day-to-day noise."
        ),
    },
)

SEVERITY_WEIGHT = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1}


def _fmt_number(value: float | None, digits: int = 1, suffix: str = "") -> str:
    """Format a number with thousands separators and an optional suffix."""
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "n/a"
    return f"{value:,.{digits}f}{suffix}"


def _fmt_p(p_value: float | None) -> str:
    """Format a p-value the way an engineer would read it."""
    if p_value is None or not np.isfinite(p_value):
        return "p = n/a"
    if p_value < 0.001:
        return "p < 0.001"
    return f"p = {p_value:.3f}"


def _pretty_date(value: str | None) -> str:
    """Render an ISO date as ``Mon DD, YYYY``."""
    if not value:
        return "n/a"
    try:
        return datetime.fromisoformat(value[:10]).strftime("%b %d, %Y")
    except ValueError:
        return value


def _severity(ooc_count: int, worst_sigma: float, run_rule_count: int) -> str:
    """Map excursion evidence to a three-level severity label."""
    if ooc_count >= 5 or abs(worst_sigma) >= 5:
        return "CRITICAL"
    if ooc_count >= 2 or abs(worst_sigma) >= 3 or run_rule_count >= 2:
        return "HIGH"
    return "MEDIUM"


def _rule_counts(violations: list[dict[str, Any]]) -> dict[str, int]:
    """Count run-rule violations by rule id."""
    counts: dict[str, int] = {}
    for item in violations:
        counts[item["rule"]] = counts.get(item["rule"], 0) + 1
    return counts


def _rank_excursions(
    tool_daily: pd.DataFrame,
    metric: str,
    fleet_mean: float,
    label: str,
    unit: str,
    digits: int = 1,
) -> list[dict[str, Any]]:
    """Build ranked plain-language excursion findings for one metric.

    Args:
        tool_daily: Columns ``tool_id``, ``date`` and ``value`` at tool-day grain.
        metric: Metric key (``throughput_wph`` or ``yield_pct``).
        fleet_mean: Fleet mean used for the relative comparison.
        label: Human label for the metric.
        unit: Unit suffix for sentences (e.g. ``" wph"``).
        digits: Decimal places for the metric value.

    Returns:
        A list of excursion dicts sorted by severity and evidence.
    """
    findings: list[dict[str, Any]] = []
    if tool_daily.empty:
        return findings
    for tool_id, group in tool_daily.groupby("tool_id", sort=True):
        group = group.sort_values("date")
        values = group["value"].dropna().tolist()
        dates = [stats._iso(d) for d in group.loc[group["value"].notna(), "date"]]
        if not values:
            continue
        chart = stats.compute_control_limits(values, sigma=3.0, dates=dates, metric=metric)
        ooc = chart["out_of_control"]
        violations = chart["violations"]
        rules = _rule_counts(violations)
        rule2 = rules.get("rule_2_eight_same_side", 0)
        if not ooc and not rule2:
            continue
        worst = min(ooc, key=lambda item: item["deviation_sigma"]) if ooc else None
        worst_sigma = float(worst["deviation_sigma"]) if worst else 0.0
        worst_side = "above" if worst_sigma > 0 else "below"
        side_ooc = [
            item
            for item in ooc
            if (item["deviation_sigma"] > 0) == (worst_sigma > 0)
        ]
        mean = float(np.mean(values))
        pct_vs_fleet = ((mean - fleet_mean) / fleet_mean * 100.0) if fleet_mean else None
        ooc_dates = [item["date"] for item in ooc]
        if ooc:
            ooc_values = [item["value"] for item in ooc]
            rest_values = [
                value for value, day in zip(values, dates) if day not in set(ooc_dates)
            ]
            p_value = stats.welch_t_test(ooc_values, rest_values)["p_value"]
            start_date, end_date = min(ooc_dates), max(ooc_dates)
            p_text = f" ({_fmt_p(p_value)})" if p_value is not None else ""
            sentence = (
                f"Tool {tool_id} {label} averaged {mean:,.{digits}f}{unit} over "
                f"{len(values)} days, {abs(pct_vs_fleet):.1f}% "
                f"{'below' if (pct_vs_fleet or 0) < 0 else 'above'} the fleet mean; "
                f"{len(side_ooc)} of {len(values)} days fell {worst_side} the "
                f"{'lower' if worst_side == 'below' else 'upper'} control limit (3σ), "
                f"{'bottoming' if worst_side == 'below' else 'peaking'} at "
                f"{worst['value']:,.{digits}f}{unit} ({worst_sigma:+.2f}σ) on "
                f"{_pretty_date(worst['date'])}{p_text}."
            )
            detail = (
                f"{len(violations)} run-rule violations alongside {len(ooc)} "
                f"out-of-control days in total; the excursion spans "
                f"{_pretty_date(start_date)} to {_pretty_date(end_date)}."
            )
        else:
            half = max(5, len(values) // 2)
            p_value = stats.welch_t_test(values[:half], values[-half:])["p_value"]
            start_date, end_date = dates[0], dates[-1]
            sentence = (
                f"Tool {tool_id} {label} averaged {mean:,.{digits}f}{unit}, "
                f"{abs(pct_vs_fleet):.1f}% "
                f"{'below' if (pct_vs_fleet or 0) < 0 else 'above'} the fleet mean, "
                f"with {rule2} run-rule violation(s) from sustained one-sided drift "
                f"({_fmt_p(p_value)} for the first-half versus second-half shift)."
            )
            detail = (
                f"{len(violations)} total run-rule violations between "
                f"{_pretty_date(start_date)} and {_pretty_date(end_date)}; no single "
                "day crossed the 3σ limit, so the shift is gradual rather than a step."
            )
        score = 5 * len(ooc) + 2 * rule2 + abs(worst_sigma)
        findings.append(
            {
                "tool_id": tool_id,
                "metric": metric,
                "severity": _severity(len(ooc), worst_sigma, rule2),
                "headline": sentence,
                "detail": detail,
                "deviation_sigma": round(worst_sigma, 3) if ooc else None,
                "start_date": start_date,
                "end_date": end_date,
                "score": score,
                "ooc_count": len(ooc),
                "run_rule_count": len(violations),
            }
        )
    findings.sort(
        key=lambda item: (SEVERITY_WEIGHT[item["severity"]], item["score"]), reverse=True
    )
    return findings


def build_summary(
    filters: Filters | dict[str, Any] | None = None,
    metric: str = "throughput_wph",
) -> dict[str, Any]:
    """Build the structured, plain-language report for *filters*.

    Args:
        filters: Dashboard filter set (Filters, mapping or None).
        metric: Primary metric for shift comparisons.

    Returns:
        A dict matching :class:`fabpulse.models.ReportResponse`.
    """
    filters = stats.coerce_filters(filters)
    echo = {**filters.as_dict(), "metric": metric}
    kpis = stats.availability_kpis(filters)
    pareto = stats.fault_pareto(filters)
    shifts = stats.shift_over_shift_delta(metric, filters)
    bounds = stats.date_bounds(filters)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    fleet = kpis["fleet"]
    if fleet is None:
        return {
            "generated_at": generated_at,
            "filters": echo,
            "headline": [],
            "summary_sentences": ["No events match the selected filters."],
            "excursions": [],
            "pareto_drivers": [],
            "shift_deltas": [],
            "glossary": list(GLOSSARY),
            "date_range": bounds,
            "counts": {"events": 0, "tools": 0, "days": 0},
        }

    throughput_daily = queries.daily_metric_by_tool("throughput_wph", filters)
    yield_daily = queries.daily_metric_by_tool("yield_pct", filters)
    throughput_mean = (
        float(throughput_daily["value"].dropna().mean()) if not throughput_daily.empty else 0.0
    )
    yield_mean = float(yield_daily["value"].dropna().mean()) if not yield_daily.empty else 0.0

    findings = _rank_excursions(
        throughput_daily, "throughput_wph", throughput_mean, "throughput", " wph"
    ) + _rank_excursions(yield_daily, "yield_pct", yield_mean, "yield", "%", digits=2)
    findings.sort(
        key=lambda item: (SEVERITY_WEIGHT[item["severity"]], item["score"]), reverse=True
    )
    top_findings = findings[:3]

    excursion_counts = {
        "out_of_control_points": sum(item["ooc_count"] for item in findings),
        "run_rule_violations": sum(item["run_rule_count"] for item in findings),
    }
    days = 0
    if bounds["min_date"] and bounds["max_date"]:
        days = (
            datetime.fromisoformat(bounds["max_date"]).date()
            - datetime.fromisoformat(bounds["min_date"]).date()
        ).days + 1

    yield_std = (
        float(yield_daily["value"].dropna().std(ddof=1)) if not yield_daily.empty else 0.0
    )

    headline = [
        {
            "label": "Uptime",
            "value": _fmt_number(fleet["uptime_pct"], 1, "%"),
            "detail": (
                f"Productive time across {fleet['tool_count']} tools and "
                f"{days} operational days."
            ),
        },
        {
            "label": "Availability (OEE)",
            "value": _fmt_number(fleet["availability_pct"], 1, "%"),
            "detail": "Productive time over planned production time (scheduled maintenance excluded).",
        },
        {
            "label": "MTBF",
            "value": _fmt_number(fleet["mtbf_hours"], 1, " h"),
            "detail": f"{fleet['failure_episodes']} unscheduled failure episodes observed.",
        },
        {
            "label": "MTTR",
            "value": _fmt_number(fleet["mttr_hours"], 2, " h"),
            "detail": f"{_fmt_number(fleet['unscheduled_down_hours'], 1, ' h')} of unplanned downtime.",
        },
        {
            "label": "Throughput p50",
            "value": _fmt_number(fleet["throughput_p50"], 1, " wph"),
            "detail": f"p95 is {_fmt_number(fleet['throughput_p95'], 1, ' wph')} across tool-days.",
        },
        {
            "label": "Yield",
            "value": f"{_fmt_number(fleet['avg_yield_pct'], 2, '%')} ± {_fmt_number(yield_std, 2)}",
            "detail": "Mean daily yield ± one standard deviation across tool-days.",
        },
    ]

    pareto_drivers = [
        row for row in pareto["rows"] if row["fault_code"] in set(pareto["codes_for_80"])
    ]
    significant = [item for item in shifts["tools"] for item in item["comparisons"]]
    significant = [item for item in significant if item["significant"] and item["pct_delta"] is not None]
    significant.sort(key=lambda item: (item["p_value"] if item["p_value"] is not None else 1.0, -abs(item["pct_delta"] or 0)))
    top_shift = significant[:5]

    summary_sentences: list[str] = []
    period = (
        f"{_pretty_date(bounds['min_date'])} to {_pretty_date(bounds['max_date'])}"
        if bounds["min_date"]
        else "the selected window"
    )
    summary_sentences.append(
        f"Across {fleet['tool_count']} tools over {days} operational days ({period}), "
        f"the fleet ran at {_fmt_number(fleet['uptime_pct'], 1, '%')} uptime with "
        f"{fleet['failure_episodes']} unscheduled failures, MTBF "
        f"{_fmt_number(fleet['mtbf_hours'], 1, ' h')} and MTTR "
        f"{_fmt_number(fleet['mttr_hours'], 2, ' h')}."
    )
    summary_sentences.append(
        f"Fleet throughput averaged {_fmt_number(fleet['avg_throughput_wph'], 1, ' wafers/hour')} "
        f"(median {_fmt_number(fleet['throughput_p50'], 1)}, p95 "
        f"{_fmt_number(fleet['throughput_p95'], 1)}), while yield averaged "
        f"{_fmt_number(fleet['avg_yield_pct'], 2, '%')} ± {_fmt_number(yield_std, 2)} "
        f"across tool-days."
    )
    if not top_findings:
        summary_sentences.append(
            "No tool crossed its 3σ control limits or produced eight consecutive "
            "one-sided points in this window, so the process looks statistically stable."
        )
    for finding in top_findings:
        summary_sentences.append(finding["headline"])
    if pareto["total_events"]:
        lead = pareto["rows"][0]
        summary_sentences.append(
            f"{len(pareto['codes_for_80'])} of {pareto['n_codes']} fault codes account for "
            f"80% of {pareto['total_events']:,} fault events; {lead['fault_code']} leads with "
            f"{lead['count']:,} events ({lead['pct_of_total']:.1f}%)."
        )
    if significant:
        strongest = significant[0]
        direction = "higher" if strongest["abs_delta"] > 0 else "lower"
        summary_sentences.append(
            f"The largest handoff effect is {strongest['from_shift']}→{strongest['to_shift']} "
            f"on {strongest['tool_id']}: {direction} by "
            f"{abs(strongest['pct_delta']):.1f}% "
            f"({_fmt_number(strongest['from_mean'], 1)} → "
            f"{_fmt_number(strongest['to_mean'], 1)}), {_fmt_p(strongest['p_value'])}."
        )

    excursions = [
        {key: value for key, value in finding.items() if key not in ("score", "ooc_count", "run_rule_count")}
        for finding in top_findings
    ]
    for index, excursion in enumerate(excursions, start=1):
        excursion["rank"] = index

    return {
        "generated_at": generated_at,
        "filters": echo,
        "headline": headline,
        "summary_sentences": summary_sentences,
        "excursions": excursions,
        "pareto_drivers": pareto_drivers,
        "shift_deltas": top_shift,
        "glossary": list(GLOSSARY),
        "date_range": bounds,
        "counts": {
            "events": fleet["events"],
            "tools": fleet["tool_count"],
            "days": days,
            "fault_events": pareto["total_events"],
            "fault_codes": pareto["n_codes"],
            **excursion_counts,
        },
    }
