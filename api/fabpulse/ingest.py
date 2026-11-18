"""Raw-log ingestion into the FabPulse star-schema warehouse.

The pipeline is deliberately explicit:

1. Read CSV or Parquet (Parquet preferred when both exist).
2. Validate and clean with documented, independently counted rejection rules.
3. Build conformed dimensions and assign surrogate keys.
4. Bulk-insert facts in chunks inside one transaction.

Re-running with ``--truncate`` rebuilds the warehouse from scratch and yields
identical counts, which is what the idempotency test asserts.

Usage:
    cd api
    python -m fabpulse.ingest --src ../data/raw --truncate
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import Engine, func, insert, select

from . import db
from .schema import (
    FAULT_ROWS,
    SHIFT_ROWS,
    STATES,
    dim_date,
    dim_fault,
    dim_shift,
    dim_tool,
    fact_tool_event,
    operational_date,
)

logger = logging.getLogger(__name__)

#: Rejection reasons, in the order the rules are applied.  A row that violates
#: several rules is counted once, under the first rule it fails.
REJECT_REASONS: tuple[str, ...] = (
    "duplicate_event_id",
    "null_timestamp",
    "negative_duration",
    "out_of_range_yield",
    "unknown_state",
    "unknown_shift",
    "missing_tool_id",
    "unknown_fault_code",
)

REQUIRED_COLUMNS: tuple[str, ...] = (
    "event_id",
    "timestamp",
    "tool_id",
    "tool_family",
    "fab_site",
    "shift",
    "state",
    "fault_code",
    "wafers_processed",
    "throughput_wph",
    "yield_pct",
    "recipe_id",
    "duration_s",
)

STRING_COLUMNS: tuple[str, ...] = (
    "event_id",
    "tool_id",
    "tool_family",
    "fab_site",
    "shift",
    "state",
    "fault_code",
    "recipe_id",
)

FACT_COLUMNS: tuple[str, ...] = (
    "event_key",
    "tool_key",
    "date_key",
    "shift_key",
    "fault_key",
    "ts",
    "state",
    "wafers_processed",
    "throughput_wph",
    "yield_pct",
    "duration_s",
    "recipe_id",
)


@dataclass
class RejectReport:
    """Counts of raw rows dropped by each ingestion rule."""

    rows_read: int = 0
    reasons: dict[str, int] = field(
        default_factory=lambda: {reason: 0 for reason in REJECT_REASONS}
    )

    @property
    def rejected(self) -> int:
        """Total rows dropped across every rule."""
        return sum(self.reasons.values())

    @property
    def rows_loaded(self) -> int:
        """Rows that survived cleaning."""
        return self.rows_read - self.rejected

    def add(self, reason: str, count: int) -> int:
        """Record *count* rejections for *reason* and return the count."""
        count = int(count)
        if count:
            self.reasons[reason] = self.reasons.get(reason, 0) + count
        return count

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly summary of the report."""
        return {
            "rows_read": self.rows_read,
            "rows_loaded": self.rows_loaded,
            "rows_rejected": self.rejected,
            "reasons": dict(self.reasons),
        }


@dataclass
class IngestResult:
    """Outcome of one ingestion run."""

    source: str
    format: str
    report: RejectReport
    elapsed_s: float
    rows_per_second: float
    warehouse_counts: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly summary of the run."""
        return {
            "source": self.source,
            "format": self.format,
            **self.report.as_dict(),
            "elapsed_s": round(self.elapsed_s, 3),
            "rows_per_second": round(self.rows_per_second, 1),
            "warehouse_counts": self.warehouse_counts,
        }


def resolve_source(src: str | Path, fmt: str = "auto") -> tuple[Path, str]:
    """Resolve a directory/file source to a concrete file and format.

    Args:
        src: Directory containing ``equipment_events.parquet``/``.csv`` or a
            direct file path.
        fmt: ``auto``, ``parquet`` or ``csv``.

    Returns:
        ``(path, format)``.

    Raises:
        FileNotFoundError: If no matching file exists.
        ValueError: For an unsupported format.
    """
    path = Path(src)
    if path.is_dir():
        if fmt in ("auto", "parquet") and (path / "equipment_events.parquet").exists():
            return path / "equipment_events.parquet", "parquet"
        if fmt in ("auto", "csv") and (path / "equipment_events.csv").exists():
            return path / "equipment_events.csv", "csv"
        raise FileNotFoundError(
            f"no equipment_events.parquet or .csv found in {path.resolve()}"
        )
    if not path.exists():
        raise FileNotFoundError(f"source file not found: {path}")
    suffix = path.suffix.lower()
    if fmt == "auto":
        fmt = "parquet" if suffix == ".parquet" else "csv"
    if fmt not in ("csv", "parquet"):
        raise ValueError(f"unsupported format: {fmt}")
    return path, fmt


def load_raw(src: str | Path, fmt: str = "auto") -> tuple[pd.DataFrame, Path, str]:
    """Load the raw log file with string dtypes preserved for validation.

    Args:
        src: Source directory or file.
        fmt: ``auto``, ``parquet`` or ``csv``.

    Returns:
        ``(dataframe, path, format)``.
    """
    path, resolved_format = resolve_source(src, fmt)
    if resolved_format == "parquet":
        frame = pd.read_parquet(path)
    else:
        frame = pd.read_csv(path, dtype={column: str for column in STRING_COLUMNS})
    return frame, path, resolved_format


def _require_columns(frame: pd.DataFrame) -> None:
    """Raise ``ValueError`` when the raw file is missing required columns."""
    missing = sorted(set(REQUIRED_COLUMNS) - set(frame.columns))
    if missing:
        raise ValueError(f"raw data is missing required columns: {', '.join(missing)}")


def clean_events(raw: pd.DataFrame) -> tuple[pd.DataFrame, RejectReport]:
    """Validate and clean raw events, counting each rejection reason.

    Rules, applied in order:
        * ``duplicate_event_id`` — ``event_id`` is null or repeated.
        * ``null_timestamp`` — timestamp empty, malformed or unparseable.
        * ``negative_duration`` — duration missing or below zero.
        * ``out_of_range_yield`` — non-null yield outside ``[0, 100]``.
        * ``unknown_state`` — state missing or outside the five known states.
        * ``unknown_shift`` — shift code missing or outside A/B/C.
        * ``missing_tool_id`` — tool/family/site identity missing.
        * ``unknown_fault_code`` — fault code not in the fixed vocabulary.

    Args:
        raw: Raw DataFrame as read from disk.

    Returns:
        A cleaned DataFrame with parsed timestamps and numeric columns, plus a
        :class:`RejectReport`.  ``len(cleaned) == report.rows_loaded``.
    """
    _require_columns(raw)
    report = RejectReport(rows_read=len(raw))
    frame = raw.copy()

    for column in STRING_COLUMNS:
        frame[column] = frame[column].astype("string").str.strip()
    frame["event_id"] = frame["event_id"].str.upper()
    frame["tool_id"] = frame["tool_id"].str.upper()
    frame["tool_family"] = frame["tool_family"].str.upper()
    frame["fab_site"] = frame["fab_site"].str.upper()
    frame["shift"] = frame["shift"].str.upper()
    frame["state"] = frame["state"].str.upper()
    frame["fault_code"] = frame["fault_code"].str.upper()

    # 1) Duplicate or missing event ids.
    duplicates = frame["event_id"].isna() | frame.duplicated(subset=["event_id"], keep="first")
    report.add("duplicate_event_id", duplicates.sum())
    frame = frame.loc[~duplicates].copy()

    # 2) Timestamps must parse as UTC datetimes.
    parsed = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True, format="mixed")
    bad_timestamp = parsed.isna()
    report.add("null_timestamp", bad_timestamp.sum())
    frame = frame.loc[~bad_timestamp].copy()
    parsed = parsed.loc[~bad_timestamp]
    frame["ts"] = parsed

    # 3) Durations must be present and non-negative.
    duration = pd.to_numeric(frame["duration_s"], errors="coerce")
    bad_duration = duration.isna() | (duration < 0)
    report.add("negative_duration", bad_duration.sum())
    frame = frame.loc[~bad_duration].copy()
    duration = duration.loc[~bad_duration]
    frame["duration_s"] = duration.astype("int64")

    # 4) Yield must be absent or inside [0, 100].
    yields = pd.to_numeric(frame["yield_pct"], errors="coerce")
    bad_yield = yields.notna() & ((yields < 0) | (yields > 100))
    report.add("out_of_range_yield", bad_yield.sum())
    frame = frame.loc[~bad_yield].copy()
    yields = yields.loc[~bad_yield]
    frame["yield_pct"] = yields

    # 5) State must be one of the five known states.
    bad_state = frame["state"].isna() | ~frame["state"].isin(STATES)
    report.add("unknown_state", bad_state.sum())
    frame = frame.loc[~bad_state].copy()

    # 6) Shift must be A/B/C.
    bad_shift = frame["shift"].isna() | ~frame["shift"].isin(["A", "B", "C"])
    report.add("unknown_shift", bad_shift.sum())
    frame = frame.loc[~bad_shift].copy()

    # 7) Tool identity must be present.
    bad_tool = (
        frame["tool_id"].isna()
        | frame["tool_family"].isna()
        | frame["fab_site"].isna()
    )
    report.add("missing_tool_id", bad_tool.sum())
    frame = frame.loc[~bad_tool].copy()

    # 8) Fault codes must belong to the fixed vocabulary (null is allowed).
    known_faults = {row[0] for row in FAULT_ROWS}
    bad_fault = frame["fault_code"].notna() & ~frame["fault_code"].isin(known_faults)
    report.add("unknown_fault_code", bad_fault.sum())
    frame = frame.loc[~bad_fault].copy()

    # Numeric hygiene for the remaining rows.
    frame["wafers_processed"] = (
        pd.to_numeric(frame["wafers_processed"], errors="coerce").fillna(0).clip(lower=0).astype("int64")
    )
    frame["throughput_wph"] = (
        pd.to_numeric(frame["throughput_wph"], errors="coerce").fillna(0.0).clip(lower=0).astype(float)
    )
    frame["fault_code"] = frame["fault_code"].where(frame["fault_code"].notna(), None)
    frame["recipe_id"] = frame["recipe_id"].where(frame["recipe_id"].notna(), None)
    frame = frame.reset_index(drop=True)

    if len(frame) != report.rows_loaded:  # pragma: no cover - invariant guard
        raise RuntimeError(
            f"cleaning invariant broken: loaded={len(frame)} expected={report.rows_loaded}"
        )
    return frame, report


def _install_date(tool_id: str, first_seen: date) -> date:
    """Derive a deterministic synthetic install date before the observation window."""
    digest = int(hashlib.sha256(tool_id.encode()).hexdigest()[:6], 16)
    return first_seen - timedelta(days=60 + digest % 700)


def build_dimensions(
    events: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Build the four dimension tables from cleaned events.

    The date dimension covers every operational day between the first and last
    observed day (no gaps), and the fault/shift dimensions are fixed
    vocabularies so the Pareto denominator is complete.

    Args:
        events: Cleaned events with parsed ``ts``.

    Returns:
        Mapping of table name to dimension DataFrame.
    """
    tools = (
        events.groupby(["tool_id", "tool_family", "fab_site"], as_index=False)
        .agg(first_seen=("ts", "min"))
        .sort_values("tool_id")
        .reset_index(drop=True)
    )
    tools["tool_key"] = np.arange(1, len(tools) + 1, dtype=int)
    tools["install_date"] = [
        _install_date(row.tool_id, row.first_seen.date())
        for row in tools.itertuples(index=False)
    ]

    operational = events["operational_date"]
    min_day, max_day = operational.min(), operational.max()
    days = pd.date_range(min_day, max_day, freq="D").date
    dates = pd.DataFrame({"date": days})
    dates["date_key"] = [
        d.year * 10000 + d.month * 100 + d.day for d in dates["date"]
    ]
    dates["year"] = [d.year for d in dates["date"]]
    dates["month"] = [d.month for d in dates["date"]]
    dates["iso_week"] = [d.isocalendar().week for d in dates["date"]]
    dates["day_of_week"] = [d.isoweekday() for d in dates["date"]]
    dates["is_weekend"] = [d.isoweekday() >= 6 for d in dates["date"]]

    shifts = pd.DataFrame(SHIFT_ROWS, columns=["shift_key", "shift_code", "start_hour", "end_hour"])
    faults = pd.DataFrame(
        [(index + 1, *row) for index, row in enumerate(FAULT_ROWS)],
        columns=["fault_key", "fault_code", "fault_category", "severity"],
    )
    return {
        "dim_tool": tools[["tool_key", "tool_id", "tool_family", "fab_site", "install_date"]],
        "dim_date": dates,
        "dim_shift": shifts,
        "dim_fault": faults,
    }


def build_facts(
    events: pd.DataFrame,
    dimensions: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Assign surrogate keys and assemble the fact table.

    Args:
        events: Cleaned events with ``ts`` and ``operational_date``.
        dimensions: Output of :func:`build_dimensions`.

    Returns:
        Fact rows sorted by tool and timestamp, with an integer ``event_key``.
    """
    tool_keys = dimensions["dim_tool"].set_index("tool_id")["tool_key"]
    fault_keys = dimensions["dim_fault"].set_index("fault_code")["fault_key"]
    shift_keys = dimensions["dim_shift"].set_index("shift_code")["shift_key"]

    facts = pd.DataFrame(
        {
            "tool_key": events["tool_id"].map(tool_keys).astype(int),
            "date_key": [
                d.year * 10000 + d.month * 100 + d.day for d in events["operational_date"]
            ],
            "shift_key": events["shift"].map(shift_keys).astype(int),
            "fault_key": events["fault_code"].map(fault_keys),
            "ts": events["ts"],
            "state": events["state"].astype(str),
            "wafers_processed": events["wafers_processed"].astype("int64"),
            "throughput_wph": events["throughput_wph"].astype(float),
            "yield_pct": events["yield_pct"].astype(float),
            "duration_s": events["duration_s"].astype("int64"),
            "recipe_id": events["recipe_id"],
        }
    )
    facts = facts.sort_values(["tool_key", "ts"], kind="stable").reset_index(drop=True)
    facts.insert(0, "event_key", np.arange(1, len(facts) + 1, dtype=np.int64))
    return facts


def _to_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a DataFrame slice to plain-Python SQLAlchemy records."""
    records = frame.to_dict(orient="records")
    for record in records:
        for key, value in list(record.items()):
            if isinstance(value, np.generic):
                record[key] = value.item()
        if record.get("fault_key") is not None and pd.isna(record["fault_key"]):
            record["fault_key"] = None
        value = record.get("yield_pct")
        if value is not None and pd.isna(value):
            record["yield_pct"] = None
        if isinstance(record.get("ts"), pd.Timestamp):
            record["ts"] = record["ts"].to_pydatetime()
    return records


def load_warehouse(
    events: pd.DataFrame,
    dimensions: dict[str, pd.DataFrame],
    engine: Engine | None = None,
    truncate: bool = False,
    chunk_size: int = 10_000,
) -> dict[str, int]:
    """Insert dimensions and facts; optionally rebuild the warehouse first.

    Args:
        events: Cleaned events.
        dimensions: Dimension DataFrames.
        engine: Target engine (defaults to the resolved warehouse).
        truncate: Drop and recreate every table before loading.
        chunk_size: Fact rows per executemany batch.

    Returns:
        Row counts per warehouse table after loading.

    Raises:
        RuntimeError: When the fact table already has rows and ``truncate`` is
            false (prevents accidental double loads).
    """
    engine = engine or db.get_engine()
    if truncate:
        db.drop_all(engine)
        db.create_all(engine)
    else:
        db.create_all(engine)
        with engine.connect() as conn:
            existing = conn.execute(select(func.count()).select_from(fact_tool_event)).scalar_one()
        if existing:
            raise RuntimeError(
                f"fact_tool_event already contains {existing:,} rows; "
                "re-run with --truncate to rebuild the warehouse"
            )

    facts = build_facts(events, dimensions)

    # SQLite cannot store timezone offsets in a DATETIME column; both backends
    # store UTC, so strip the tzinfo only for SQLite.
    if engine.dialect.name == "sqlite":
        facts["ts"] = facts["ts"].dt.tz_localize(None)

    with engine.begin() as conn:
        conn.execute(insert(dim_tool), _to_records(dimensions["dim_tool"]))
        conn.execute(insert(dim_date), _to_records(dimensions["dim_date"]))
        conn.execute(insert(dim_shift), _to_records(dimensions["dim_shift"]))
        conn.execute(insert(dim_fault), _to_records(dimensions["dim_fault"]))
        columns = list(FACT_COLUMNS)
        for start in range(0, len(facts), chunk_size):
            chunk = facts.iloc[start : start + chunk_size]
            conn.execute(
                insert(fact_tool_event),
                _to_records(chunk[columns]),
            )

    with engine.connect() as conn:
        counts = {
            "dim_tool": int(conn.execute(select(func.count()).select_from(dim_tool)).scalar_one()),
            "dim_date": int(conn.execute(select(func.count()).select_from(dim_date)).scalar_one()),
            "dim_shift": int(conn.execute(select(func.count()).select_from(dim_shift)).scalar_one()),
            "dim_fault": int(conn.execute(select(func.count()).select_from(dim_fault)).scalar_one()),
            "fact_tool_event": int(
                conn.execute(select(func.count()).select_from(fact_tool_event)).scalar_one()
            ),
        }
    return counts


def run_ingest(
    src: str | Path,
    fmt: str = "auto",
    truncate: bool = False,
    engine: Engine | None = None,
    chunk_size: int = 10_000,
) -> IngestResult:
    """Run the full load and return a summary (used by the CLI and tests).

    Args:
        src: Raw directory or file.
        fmt: ``auto``, ``csv`` or ``parquet``.
        truncate: Rebuild the warehouse first.
        engine: Optional engine override.
        chunk_size: Fact insert batch size.

    Returns:
        An :class:`IngestResult` with counts and timing.
    """
    started = time.perf_counter()
    raw, path, resolved_format = load_raw(src, fmt)
    events, report = clean_events(raw)
    events["operational_date"] = [
        operational_date(ts, shift) for ts, shift in zip(events["ts"], events["shift"])
    ]
    dimensions = build_dimensions(events)
    counts = load_warehouse(
        events,
        dimensions,
        engine=engine,
        truncate=truncate,
        chunk_size=chunk_size,
    )
    elapsed = time.perf_counter() - started
    result = IngestResult(
        source=str(path),
        format=resolved_format,
        report=report,
        elapsed_s=elapsed,
        rows_per_second=(report.rows_loaded / elapsed) if elapsed > 0 else 0.0,
        warehouse_counts=counts,
    )
    return result


def _print_summary(result: IngestResult) -> None:
    """Print the ingestion summary in a stable, human-readable format."""
    report = result.report
    print("FabPulse ingestion summary")
    print(f"  source            : {result.source} ({result.format})")
    print(f"  rows read         : {report.rows_read:,}")
    print(f"  rows loaded       : {report.rows_loaded:,}")
    print(f"  rows rejected     : {report.rejected:,}")
    for reason, count in report.reasons.items():
        print(f"    - {reason:<20}: {count:,}")
    print(f"  elapsed           : {result.elapsed_s:.2f} s")
    print(f"  throughput        : {result.rows_per_second:,.0f} rows/s")
    print(
        "  warehouse rows    : "
        + ", ".join(f"{name}={count:,}" for name, count in result.warehouse_counts.items())
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for ``python -m fabpulse.ingest``."""
    parser = argparse.ArgumentParser(description="Ingest FabPulse raw equipment logs")
    parser.add_argument("--src", default="data/raw", help="raw directory or file")
    parser.add_argument(
        "--format", default="auto", choices=("auto", "csv", "parquet"), dest="fmt"
    )
    parser.add_argument(
        "--truncate", action="store_true", help="drop and rebuild every warehouse table"
    )
    parser.add_argument("--chunk-size", type=int, default=10_000, help="fact rows per batch")
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        result = run_ingest(
            args.src, fmt=args.fmt, truncate=args.truncate, chunk_size=args.chunk_size
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ingestion failed: {exc}", file=sys.stderr)
        return 1
    _print_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
