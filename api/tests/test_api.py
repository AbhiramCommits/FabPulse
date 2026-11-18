"""HTTP contract tests for every FabPulse endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_health(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "sqlite"
    assert body["warehouse_rows"] > 0


def test_meta_filters(client: TestClient):
    body = client.get("/api/meta/filters").json()
    assert len(body["tools"]) == 6
    assert body["families"] == ["METRO", "SCANNER", "TRACK"]
    assert set(body["sites"]) == {"FAB-A", "FAB-B"}
    assert [shift["shift_code"] for shift in body["shifts"]] == ["A", "B", "C"]
    assert len(body["fault_codes"]) == 15
    assert body["date_bounds"]["min_date"] <= body["date_bounds"]["max_date"]


def test_kpis_shape_and_pagination(client: TestClient):
    first = client.get("/api/kpis", params={"page": 1, "page_size": 2}).json()
    assert first["fleet"]["tool_count"] == 6
    assert first["tools_total"] == 6
    assert len(first["tools"]) == 2
    assert first["page"] == 1 and first["page_size"] == 2
    second = client.get("/api/kpis", params={"page": 2, "page_size": 2}).json()
    assert len(second["tools"]) == 2
    assert {row["tool_id"] for row in first["tools"]} != {
        row["tool_id"] for row in second["tools"]
    }
    sorted_page = client.get(
        "/api/kpis",
        params={"page_size": 6, "sort_by": "uptime_pct", "sort_dir": "desc"},
    ).json()
    uptimes = [row["uptime_pct"] for row in sorted_page["tools"]]
    assert uptimes == sorted(uptimes, reverse=True)


def test_kpis_filter_propagation(client: TestClient):
    body = client.get(
        "/api/kpis",
        params={"tool_family": "SCANNER", "shifts": ["A"], "metric": "yield_pct"},
    ).json()
    assert body["filters"]["tool_family"] == "SCANNER"
    assert body["filters"]["shifts"] == ["A"]
    assert body["filters"]["metric"] == "yield_pct"
    assert {row["tool_family"] for row in body["tools"]} == {"SCANNER"}


def test_timeseries_shape_and_filter_effect(client: TestClient):
    body = client.get("/api/timeseries", params={"window": 5, "sigma": 3}).json()
    assert body["metric"] == "throughput_wph"
    assert body["window"] == 5
    assert len(body["series"]) == 10
    assert body["ucl"] > body["lcl"]
    assert body["series"][0]["rolling_std"] is None

    filtered = client.get(
        "/api/timeseries", params={"tool_ids": ["METRO-01"], "metric": "yield_pct"}
    ).json()
    assert filtered["filters"]["tool_ids"] == ["METRO-01"]
    assert filtered["metric"] == "yield_pct"
    assert filtered["center"] != body["center"]


def test_boxplot_shape(client: TestClient):
    body = client.get("/api/boxplot", params={"metric": "yield_pct"}).json()
    assert body["metric"] == "yield_pct"
    assert len(body["tools"]) == 6
    tool = body["tools"][0]
    for key in ("min", "q1", "median", "q3", "max", "lower_fence", "upper_fence"):
        assert key in tool
    assert body["fleet"]["count"] > 0


def test_pareto_shape(client: TestClient):
    body = client.get("/api/pareto").json()
    assert body["total_events"] > 0
    assert body["n_codes"] == len(body["rows"])
    assert body["rows"][0]["cumulative_pct"] == body["rows"][0]["pct_of_total"]
    assert body["rows"][-1]["cumulative_pct"] == pytest.approx(100.0, abs=0.01)


def test_heatmap_shape(client: TestClient):
    body = client.get("/api/heatmap").json()
    assert len(body["tools"]) == 6
    assert body["shifts"] == ["A", "B", "C"]
    assert len(body["tool_shift"]) == 6
    assert all(len(row) == 3 for row in body["tool_shift"])
    assert body["max_count"] > 0


def test_shift_delta_endpoint(client: TestClient):
    body = client.get("/api/shifts/delta").json()
    assert len(body["tools"]) == 6
    assert body["strongest"] is not None
    assert {"from_shift", "to_shift", "p_value", "significant"} <= set(body["strongest"])


def test_tool_events_pagination_and_sorting(client: TestClient):
    first = client.get(
        "/api/tools/SCANNER-01/events", params={"page": 1, "page_size": 5}
    ).json()
    assert first["tool_id"] == "SCANNER-01"
    assert first["page"] == 1 and first["page_size"] == 5
    assert first["total"] > 5
    assert first["total_pages"] >= 2
    assert len(first["rows"]) == 5
    assert first["rows"][0]["ts"] >= first["rows"][-1]["ts"]

    second = client.get(
        "/api/tools/SCANNER-01/events", params={"page": 2, "page_size": 5}
    ).json()
    assert {row["event_key"] for row in first["rows"]}.isdisjoint(
        {row["event_key"] for row in second["rows"]}
    )

    sorted_page = client.get(
        "/api/tools/SCANNER-01/events",
        params={"page_size": 20, "sort_by": "throughput_wph", "sort_dir": "desc"},
    ).json()
    values = [row["throughput_wph"] for row in sorted_page["rows"]]
    assert values == sorted(values, reverse=True)


def test_events_filter_propagation(client: TestClient):
    bounds = client.get("/api/meta/filters").json()["date_bounds"]
    body = client.get(
        "/api/tools/SCANNER-01/events",
        params={
            "shifts": ["C"],
            "from_date": bounds["min_date"],
            "to_date": bounds["max_date"],
            "page_size": 50,
        },
    ).json()
    assert body["rows"]
    assert all(row["shift"] == "C" for row in body["rows"])
    assert all(row["ts"][:10] >= bounds["min_date"] for row in body["rows"])


def test_report_summary_shape(client: TestClient):
    body = client.get("/api/report/summary").json()
    assert body["headline"]
    assert body["summary_sentences"]
    assert body["glossary"]
    terms = [entry["term"] for entry in body["glossary"]]
    assert {"UCL / LCL", "MTBF", "MTTR", "IQR", "p-value"} <= set(terms)
    assert body["counts"]["tools"] == 6
    assert body["date_range"]["min_date"] <= body["date_range"]["max_date"]


def test_bad_filters_return_400(client: TestClient):
    bad_range = client.get(
        "/api/kpis", params={"from_date": "2026-02-01", "to_date": "2026-01-01"}
    )
    assert bad_range.status_code == 400
    assert "from_date" in bad_range.json()["detail"]

    bad_shift = client.get("/api/kpis", params={"shifts": ["Z"]})
    assert bad_shift.status_code == 400

    bad_metric = client.get("/api/timeseries", params={"metric": "nope"})
    assert bad_metric.status_code == 400

    bad_date = client.get("/api/kpis", params={"from_date": "not-a-date"})
    assert bad_date.status_code == 400

    bad_window = client.get("/api/timeseries", params={"window": 0})
    assert bad_window.status_code == 400


def test_bad_event_params_and_unknown_tool(client: TestClient):
    assert client.get("/api/tools/NOPE-99/events").status_code == 404
    assert (
        client.get("/api/tools/SCANNER-01/events", params={"sort_by": "drop table"})
        .status_code
        == 400
    )
    assert (
        client.get("/api/tools/SCANNER-01/events", params={"page": 0}).status_code == 400
    )
    assert (
        client.get("/api/kpis", params={"sort_by": "not_a_column"}).status_code == 400
    )


def test_openapi_contract(client: TestClient):
    spec = client.get("/openapi.json").json()
    expected = {
        "/api/health",
        "/api/meta/filters",
        "/api/kpis",
        "/api/timeseries",
        "/api/boxplot",
        "/api/pareto",
        "/api/heatmap",
        "/api/tools/{tool_id}/events",
        "/api/report/summary",
    }
    assert expected <= set(spec["paths"])
