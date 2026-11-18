"""Report payload and exporter tests (Markdown, CSV, JSON, CLI)."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from fabpulse import report
from fabpulse.filters import Filters

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_exporter():
    spec = importlib.util.spec_from_file_location(
        "fabpulse_export_report", REPO_ROOT / "scripts" / "export_report.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


export_report = _load_exporter()


def test_build_summary_structure(warehouse):
    data = report.build_summary()
    assert data["filters"]["metric"] == "throughput_wph"
    assert len(data["headline"]) == 6
    assert len(data["summary_sentences"]) >= 4
    assert len(data["excursions"]) <= 3
    assert data["pareto_drivers"]
    assert data["shift_deltas"]
    terms = {entry["term"] for entry in data["glossary"]}
    assert {"UCL / LCL", "MTBF", "MTTR", "IQR", "p-value"} <= terms
    assert any("throughput" in sentence.lower() for sentence in data["summary_sentences"])
    assert any("yield" in sentence.lower() for sentence in data["summary_sentences"])
    assert all(item["rank"] >= 1 for item in data["excursions"])


def test_build_summary_empty_filter(warehouse):
    data = report.build_summary(Filters(tool_ids=("NOPE-99",)))
    assert data["headline"] == []
    assert "No events match" in data["summary_sentences"][0]


def test_markdown_contains_real_sections(warehouse):
    data = report.build_summary()
    text = export_report.render_markdown(data)
    assert text.startswith("# FabPulse engineer report")
    assert "## Headline KPIs" in text
    assert "## What the data says" in text
    assert "## Pareto: fault codes behind 80% of events" in text
    assert "## Glossary" in text
    assert "MTTR" in text
    assert str(data["counts"]["events"]) in text.replace(",", "") or "Events:" in text


def test_csv_is_tidy_and_parseable(warehouse):
    data = report.build_summary()
    text = export_report.render_csv(data)
    rows = list(csv.reader(text.splitlines()))
    assert rows[0] == ["section", "item", "detail", "value"]
    sections = {row[0] for row in rows[1:]}
    expected = {"headline", "summary", "pareto", "shift_delta", "glossary"}
    if data["excursions"]:
        expected.add("excursion")
    assert expected <= sections
    assert len(rows) > 20


def test_write_report_all_formats(warehouse, tmp_path):
    data = report.build_summary()
    markdown_path = export_report.write_report(data, "md", tmp_path)
    csv_path = export_report.write_report(data, "csv", tmp_path)
    json_path = export_report.write_report(data, "json", tmp_path)

    assert markdown_path.exists() and markdown_path.suffix == ".md"
    assert csv_path.exists() and csv_path.suffix == ".csv"
    assert json.loads(json_path.read_text())["counts"]["tools"] == 6
    with pytest.raises(ValueError):
        export_report.write_report(data, "xlsx", tmp_path)


def test_export_cli(warehouse, tmp_path, capsys):
    code = export_report.main(["--format", "json", "--out", str(tmp_path)])
    assert code == 0
    captured = capsys.readouterr().out
    assert "wrote" in captured
    assert (tmp_path / "fabpulse_report.json").exists()

    bad = export_report.main(
        ["--format", "md", "--from-date", "2026-02-01", "--to-date", "2026-01-01"]
    )
    assert bad == 1
