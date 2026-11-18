"""Statistics: pure math on known arrays plus integration on the warehouse."""

from __future__ import annotations

import math

import numpy as np
import pytest

from fabpulse import stats
from fabpulse.filters import Filters


def test_control_limits_exact_mean_and_sigma():
    """UCL/LCL equal mean ± 3 sample standard deviations, exactly."""
    values = [10.0, 12.0, 11.0, 13.0, 12.0]
    result = stats.compute_control_limits(values, sigma=3.0)
    expected_mean = float(np.mean(values))
    expected_std = float(np.std(values, ddof=1))
    assert result["center"] == round(expected_mean, 4)
    assert result["std"] == round(expected_std, 4)
    assert result["ucl"] == round(expected_mean + 3 * expected_std, 4)
    assert result["lcl"] == round(expected_mean - 3 * expected_std, 4)
    assert result["sigma"] == 3.0


def test_control_limits_handles_empty_and_single_point():
    empty = stats.compute_control_limits([])
    assert empty["center"] is None and empty["points"] == []
    single = stats.compute_control_limits([5.0])
    assert single["std"] == 0.0
    assert single["ucl"] == single["lcl"] == 5.0


def test_run_rule_eight_consecutive_same_side():
    """Eight points above the center trigger rule 2 exactly once."""
    values = [-0.2, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, -0.1]
    violations = stats.detect_run_rules(values, center=0.0, sigma=1.0)
    rules = [item["rule"] for item in violations]
    assert "rule_2_eight_same_side" in rules
    assert rules.count("rule_2_eight_same_side") == 1


def test_run_rule_points_beyond_three_sigma():
    """A point beyond the 3σ limit is flagged as rule 1."""
    values = [0.0, 0.1, -0.1, 3.6, 0.2]
    violations = stats.detect_run_rules(values, center=0.0, sigma=1.0)
    rule_one = [item for item in violations if item["rule"] == "rule_1_3sigma"]
    assert len(rule_one) == 1
    assert rule_one[0]["value"] == 3.6


def test_run_rule_two_of_three_beyond_two_sigma():
    """Two of three points beyond 2σ on the same side triggers rule 3."""
    values = [0.0, 0.0, 2.1, 0.1, 2.3]
    violations = stats.detect_run_rules(values, center=0.0, sigma=1.0)
    assert any(item["rule"] == "rule_3_two_of_three_2sigma" for item in violations)


def test_percentiles_and_iqr_outlier_on_known_array():
    """Known percentiles/fences and a single Tukey outlier at 100."""
    summary, outliers = stats.tukey_outliers(
        [1, 2, 3, 4, 5, 6, 7, 8, 9, 100], [f"2026-01-{day:02d}" for day in range(1, 11)]
    )
    assert summary["median"] == 5.5
    assert summary["q1"] == 3.25
    assert summary["q3"] == 7.75
    assert summary["iqr"] == 4.5
    assert summary["lower_fence"] == -3.5
    assert summary["upper_fence"] == 14.5
    assert len(outliers) == 1
    assert outliers[0]["value"] == 100.0


def test_distribution_summary_requires_values():
    with pytest.raises(ValueError):
        stats.distribution_summary([float("nan"), None])  # type: ignore[list-item]


def test_welch_t_test_sign_and_significance():
    """A lower sample gets a negative t statistic and a tiny p-value."""
    low = [10.0, 10.2, 9.9, 10.1, 10.0, 9.8, 10.3]
    high = [12.0, 12.2, 11.9, 12.1, 12.0, 11.8, 12.3]
    result = stats.welch_t_test(low, high)
    assert result["t_statistic"] is not None and result["t_statistic"] < 0
    assert result["p_value"] is not None and result["p_value"] < 0.001
    assert result["n_a"] == 7 and result["n_b"] == 7
    same = stats.welch_t_test(low, low)
    assert same["p_value"] == 1.0


def test_welch_t_test_needs_two_observations():
    result = stats.welch_t_test([1.0], [2.0, 3.0])
    assert result["t_statistic"] is None
    assert result["p_value"] is None


def test_availability_kpis(warehouse):
    data = stats.availability_kpis()
    fleet = data["fleet"]
    assert fleet is not None
    assert fleet["tool_count"] == 6
    assert 0 < fleet["uptime_pct"] < 100
    assert fleet["failure_episodes"] > 0
    assert fleet["mtbf_hours"] > 0 and fleet["mttr_hours"] > 0
    assert fleet["throughput_p50"] is not None
    assert len(data["tools"]) == 6


def test_rolling_series(warehouse):
    frame = stats.rolling_series("throughput_wph", window=7)
    assert len(frame) == 10
    assert math.isnan(frame["rolling_std"].iloc[0])
    assert not math.isnan(frame["rolling_mean"].iloc[-1])
    with pytest.raises(ValueError):
        stats.rolling_series("throughput_wph", window=0)


def test_control_limits_from_warehouse(warehouse):
    result = stats.control_limits("yield_pct", sigma=3.0)
    assert result["n"] == 10
    assert result["ucl"] > result["lcl"]
    assert isinstance(result["violations"], list)
    with pytest.raises(ValueError):
        stats.control_limits("not_a_metric")
    with pytest.raises(ValueError):
        stats.control_limits("yield_pct", sigma=0)


def test_percentiles_outliers_from_warehouse(warehouse):
    data = stats.percentiles_outliers("throughput_wph")
    assert data["metric"] == "throughput_wph"
    assert len(data["tools"]) == 6
    assert data["fleet"] is not None
    assert data["fleet"]["q1"] <= data["fleet"]["median"] <= data["fleet"]["q3"]


def test_shift_delta_finds_significant_handoff(warehouse):
    data = stats.shift_over_shift_delta("throughput_wph")
    assert len(data["tools"]) == 6
    comparisons = [item for tool in data["tools"] for item in tool["comparisons"]]
    assert comparisons
    assert any(item["significant"] for item in comparisons)
    assert data["strongest"] is not None


def test_pareto_is_monotonic_and_ends_at_100(warehouse):
    data = stats.fault_pareto()
    cumulative = [row["cumulative_pct"] for row in data["rows"]]
    assert data["total_events"] > 0
    assert cumulative == sorted(cumulative)
    assert cumulative[-1] == pytest.approx(100.0, abs=0.01)
    assert 0 < len(data["codes_for_80"]) <= len(data["rows"])
    assert [row["fault_code"] for row in data["rows"]][: len(data["codes_for_80"])] == data[
        "codes_for_80"
    ]


def test_fault_heatmap_shapes(warehouse):
    data = stats.fault_heatmap()
    assert len(data["shifts"]) == 3
    assert len(data["tools"]) == 6
    assert len(data["tool_shift"]) == len(data["tools"])
    assert all(len(row) == 3 for row in data["tool_shift"])
    assert len(data["tool_fault"]) == len(data["tools"])
    assert all(len(row) == len(data["fault_codes"]) for row in data["tool_fault"])


def test_filter_validation_and_coercion():
    filters = Filters.from_mapping(
        {"from_date": "2026-01-01", "to_date": "2026-01-10", "tool_ids": "A,B", "shifts": ["A"]}
    )
    assert filters.tool_ids == ("A", "B")
    filters.validate()
    with pytest.raises(ValueError):
        Filters.from_mapping({"from_date": "2026-02-01", "to_date": "2026-01-01"}).validate()
    with pytest.raises(ValueError):
        Filters(shifts=("Z",)).validate()


def test_date_bounds_and_empty_filters(warehouse):
    bounds = stats.date_bounds()
    assert bounds["min_date"] is not None and bounds["max_date"] is not None
    empty = stats.availability_kpis(Filters(tool_ids=("NOPE-99",)))
    assert empty["fleet"] is None
    assert empty["tools"] == []
