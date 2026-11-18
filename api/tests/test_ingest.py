"""Ingestion: rejection accounting, idempotency, key integrity and parity."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import text

from fabpulse import db, ingest

VALID_STATE = ["PRODUCTIVE", "STANDBY", "SCHEDULED_DOWN", "UNSCHEDULED_DOWN", "ENGINEERING"]


def _row(index: int, **overrides) -> dict:
    """Build one structurally valid raw row."""
    row = {
        "event_id": f"EVT-{index:05d}",
        "timestamp": f"2026-01-0{(index % 5) + 1}T0{6 + index % 8}:00:00Z",
        "tool_id": "SCANNER-01",
        "tool_family": "SCANNER",
        "fab_site": "FAB-A",
        "shift": "A",
        "state": "PRODUCTIVE",
        "fault_code": None,
        "wafers_processed": 4,
        "throughput_wph": 48.0,
        "yield_pct": 98.4,
        "recipe_id": "RCP-LITH-114",
        "duration_s": 300,
    }
    row.update(overrides)
    return row


def test_clean_events_counts_each_rejection_reason():
    """Every documented dirty row is dropped under exactly one reason."""
    raw = pd.DataFrame(
        [
            _row(1),
            _row(2, timestamp="2026-01-02T07:00:00Z"),
            _row(3, timestamp="2026-01-03T08:00:00Z"),
            _row(1),  # duplicate event_id
            _row(4, timestamp=None),  # null timestamp
            _row(5, duration_s=-300),  # negative duration
            _row(6, yield_pct=140.0),  # out-of-range yield
            _row(7, state="MAINTENANCE"),  # unknown state
        ]
    )
    cleaned, report = ingest.clean_events(raw)

    assert report.rows_read == 8
    assert report.rows_loaded == len(cleaned) == 3
    assert report.rejected == 5
    assert report.reasons["duplicate_event_id"] == 1
    assert report.reasons["null_timestamp"] == 1
    assert report.reasons["negative_duration"] == 1
    assert report.reasons["out_of_range_yield"] == 1
    assert report.reasons["unknown_state"] == 1
    assert set(cleaned["state"]).issubset(VALID_STATE)


def test_clean_events_rejects_unparseable_timestamp():
    """Garbage date strings are counted as null timestamps, not crashes."""
    raw = pd.DataFrame(
        [
            _row(1),
            _row(2, timestamp="not-a-date"),
            _row(3, timestamp="2026-13-45T99:99:99Z"),
        ]
    )
    cleaned, report = ingest.clean_events(raw)
    assert len(cleaned) == 1
    assert report.reasons["null_timestamp"] == 2


def test_ingest_is_idempotent_with_truncate(small_raw: Path, sqlite_engine):
    """Two --truncate runs produce identical counts and warehouse contents."""
    first = ingest.run_ingest(small_raw, fmt="parquet", truncate=True, engine=sqlite_engine)
    second = ingest.run_ingest(small_raw, fmt="parquet", truncate=True, engine=sqlite_engine)

    assert first.report.as_dict() == second.report.as_dict()
    assert first.warehouse_counts == second.warehouse_counts
    assert first.warehouse_counts["fact_tool_event"] == first.report.rows_loaded

    with sqlite_engine.connect() as conn:
        checksum_one = conn.execute(
            text(
                "SELECT COUNT(*) AS n, SUM(wafers_processed) AS w, "
                "SUM(duration_s) AS d FROM fact_tool_event"
            )
        ).one()
    assert checksum_one.n == first.warehouse_counts["fact_tool_event"]
    assert checksum_one.w > 0 and checksum_one.d > 0


def test_ingest_without_truncate_refuses_double_load(small_raw: Path, sqlite_engine):
    """A second load without --truncate fails loudly instead of duplicating."""
    ingest.run_ingest(small_raw, fmt="parquet", truncate=True, engine=sqlite_engine)
    with pytest.raises(RuntimeError, match="already contains"):
        ingest.run_ingest(small_raw, fmt="parquet", truncate=False, engine=sqlite_engine)


def test_parquet_and_csv_have_parity(sample_raw, tmp_path):
    """CSV and Parquet produce the same warehouse rows and rejection counts."""
    from sqlalchemy import create_engine

    _, raw_dir = sample_raw
    csv_engine = create_engine(f"sqlite:///{tmp_path / 'csv.db'}")
    parquet_engine = create_engine(f"sqlite:///{tmp_path / 'parquet.db'}")

    csv_result = ingest.run_ingest(raw_dir, fmt="csv", truncate=True, engine=csv_engine)
    parquet_result = ingest.run_ingest(
        raw_dir, fmt="parquet", truncate=True, engine=parquet_engine
    )

    assert csv_result.report.as_dict() == parquet_result.report.as_dict()
    assert csv_result.warehouse_counts == parquet_result.warehouse_counts

    def checksum(engine):
        with engine.connect() as conn:
            return conn.execute(
                text(
                    "SELECT COUNT(*) AS n, SUM(wafers_processed) AS w, "
                    "SUM(ROUND(throughput_wph, 3)) AS t FROM fact_tool_event"
                )
            ).one()

    assert checksum(csv_engine) == checksum(parquet_engine)


def test_surrogate_keys_are_complete(warehouse):
    """No fact row points at a missing dimension key."""
    engine = db.get_engine()
    with engine.connect() as conn:
        orphan_tool = conn.execute(
            text(
                "SELECT COUNT(*) FROM fact_tool_event f LEFT JOIN dim_tool t "
                "ON t.tool_key = f.tool_key WHERE t.tool_key IS NULL"
            )
        ).scalar_one()
        orphan_date = conn.execute(
            text(
                "SELECT COUNT(*) FROM fact_tool_event f LEFT JOIN dim_date d "
                "ON d.date_key = f.date_key WHERE d.date_key IS NULL"
            )
        ).scalar_one()
        orphan_shift = conn.execute(
            text(
                "SELECT COUNT(*) FROM fact_tool_event f LEFT JOIN dim_shift s "
                "ON s.shift_key = f.shift_key WHERE s.shift_key IS NULL"
            )
        ).scalar_one()
        duplicate_keys = conn.execute(
            text(
                "SELECT COUNT(*) FROM (SELECT event_key FROM fact_tool_event "
                "GROUP BY event_key HAVING COUNT(*) > 1) dup"
            )
        ).scalar_one()
    assert orphan_tool == 0
    assert orphan_date == 0
    assert orphan_shift == 0
    assert duplicate_keys == 0
    assert warehouse.warehouse_counts["dim_shift"] == 3
    assert warehouse.warehouse_counts["dim_fault"] == 15


def test_cli_prints_summary(monkeypatch, capsys):
    """The CLI entry point prints read/loaded/rejected counts and throughput."""
    fake = ingest.IngestResult(
        source="fake.parquet",
        format="parquet",
        report=ingest.RejectReport(rows_read=10, reasons={"duplicate_event_id": 2}),
        elapsed_s=1.5,
        rows_per_second=6.0,
        warehouse_counts={"fact_tool_event": 8},
    )
    monkeypatch.setattr(ingest, "run_ingest", lambda *args, **kwargs: fake)
    code = ingest.main(["--src", "fake", "--truncate"])
    captured = capsys.readouterr().out
    assert code == 0
    assert "rows read         : 10" in captured
    assert "rows loaded       : 8" in captured
    assert "rows rejected     : 2" in captured
    assert "throughput" in captured


def test_resolve_source_errors(tmp_path: Path):
    """Missing files/directories fail with actionable errors."""
    with pytest.raises(FileNotFoundError):
        ingest.resolve_source(tmp_path / "missing.parquet")
    with pytest.raises(FileNotFoundError):
        ingest.resolve_source(tmp_path)
