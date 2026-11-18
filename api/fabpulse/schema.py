"""Star-schema warehouse definitions (SQLAlchemy Core).

Postgres is the primary target.  The same metadata creates equivalent SQLite
tables so the stack runs without a database server; see ``scripts/schema.sql``
for the canonical Postgres DDL.

Schema
------
    dim_tool  1 ──< fact_tool_event >── 1 dim_date
                  fact_tool_event  >── 1 dim_shift
                  fact_tool_event  >── 0..1 dim_fault

``date_key`` is the *operational* date: intervals belonging to the night (C)
shift before 06:00 UTC are attributed to the previous calendar day so that each
shift stays inside one analytical day.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Table,
    text,
)
from sqlalchemy.schema import CreateIndex, CreateTable

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)

#: The five valid equipment states emitted by the tools.
STATES: tuple[str, ...] = (
    "PRODUCTIVE",
    "STANDBY",
    "SCHEDULED_DOWN",
    "UNSCHEDULED_DOWN",
    "ENGINEERING",
)

#: Shift dimension rows: code, start hour (UTC), end hour (UTC).
SHIFT_ROWS: tuple[tuple[int, str, int, int], ...] = (
    (1, "A", 6, 14),
    (2, "B", 14, 22),
    (3, "C", 22, 6),
)

#: Fault dimension rows: code, category, severity.  Kept in sync with
#: ``data/generate.py`` (both are intentionally fixed vocabularies).
FAULT_ROWS: tuple[tuple[str, str, str], ...] = (
    ("VAC_LOSS", "Vacuum", "HIGH"),
    ("RF_REFLECT", "RF Power", "HIGH"),
    ("TEMP_DRIFT", "Thermal", "MEDIUM"),
    ("GAS_FLOW", "Gas Delivery", "HIGH"),
    ("CHUCK_CLAMP", "Wafer Handling", "MEDIUM"),
    ("LITHO_ALIGN", "Alignment", "HIGH"),
    ("SLIT_VALVE", "Vacuum", "CRITICAL"),
    ("ROBOT_PICK", "Wafer Handling", "CRITICAL"),
    ("PARTICLE", "Contamination", "MEDIUM"),
    ("CAL_DRIFT", "Calibration", "LOW"),
    ("PUMP_OVERHEAT", "Thermal", "HIGH"),
    ("EDGE_BEAD", "Coating", "LOW"),
    ("SENSOR_NOISE", "Instrumentation", "LOW"),
    ("LOADLOCK_LEAK", "Vacuum", "HIGH"),
    ("RECIPE_MISMATCH", "Software", "MEDIUM"),
)

dim_tool = Table(
    "dim_tool",
    metadata,
    Column("tool_key", Integer, primary_key=True),
    Column("tool_id", String(32), nullable=False, unique=True),
    Column("tool_family", String(32), nullable=False),
    Column("fab_site", String(16), nullable=False),
    Column("install_date", Date, nullable=True),
)

dim_date = Table(
    "dim_date",
    metadata,
    Column("date_key", Integer, primary_key=True),  # YYYYMMDD
    Column("date", Date, nullable=False, unique=True),
    Column("year", SmallInteger, nullable=False),
    Column("month", SmallInteger, nullable=False),
    Column("iso_week", SmallInteger, nullable=False),
    Column("day_of_week", SmallInteger, nullable=False),  # ISO: 1=Mon .. 7=Sun
    Column("is_weekend", Boolean, nullable=False),
)

dim_shift = Table(
    "dim_shift",
    metadata,
    Column("shift_key", SmallInteger, primary_key=True),
    Column("shift_code", String(1), nullable=False, unique=True),
    Column("start_hour", SmallInteger, nullable=False),
    Column("end_hour", SmallInteger, nullable=False),
)

dim_fault = Table(
    "dim_fault",
    metadata,
    Column("fault_key", SmallInteger, primary_key=True),
    Column("fault_code", String(32), nullable=False, unique=True),
    Column("fault_category", String(32), nullable=False),
    Column("severity", String(16), nullable=False),
)

fact_tool_event = Table(
    "fact_tool_event",
    metadata,
    Column("event_key", BigInteger, primary_key=True),
    Column("tool_key", Integer, ForeignKey("dim_tool.tool_key"), nullable=False),
    Column("date_key", Integer, ForeignKey("dim_date.date_key"), nullable=False),
    Column("shift_key", SmallInteger, ForeignKey("dim_shift.shift_key"), nullable=False),
    Column("fault_key", SmallInteger, ForeignKey("dim_fault.fault_key"), nullable=True),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("state", String(24), nullable=False),
    Column("wafers_processed", Integer, nullable=False, server_default=text("0")),
    Column("throughput_wph", Float, nullable=False, server_default=text("0")),
    Column("yield_pct", Float, nullable=True),
    Column("duration_s", Integer, nullable=False),
    # Degenerate dimension: the recipe is useful to engineers but not worth a
    # separate dimension table at this grain.
    Column("recipe_id", String(32), nullable=True),
)

Index("ix_fact_tool_ts", fact_tool_event.c.tool_key, fact_tool_event.c.ts)
Index(
    "ix_fact_date_shift",
    fact_tool_event.c.date_key,
    fact_tool_event.c.shift_key,
)
Index("ix_fact_fault", fact_tool_event.c.fault_key)
Index("ix_fact_state", fact_tool_event.c.state)

ALL_TABLES = (dim_tool, dim_date, dim_shift, dim_fault, fact_tool_event)


def date_key(value) -> int:
    """Convert a date/datetime to the integer ``YYYYMMDD`` date key."""
    return value.year * 10000 + value.month * 100 + value.day


def operational_date(ts, shift_code: str):
    """Return the operational date for a timestamp and shift code.

    The C shift starts at 22:00 UTC and runs past midnight; its early-morning
    intervals belong to the previous operational day.

    Args:
        ts: Timezone-aware (or naive UTC) timestamp.
        shift_code: One of ``A``, ``B`` or ``C``.

    Returns:
        A ``datetime.date``.
    """
    from datetime import timedelta

    if shift_code == "C" and ts.hour < 6:
        return (ts - timedelta(days=1)).date()
    return ts.date()


def write_postgres_ddl(out_path: str | Path) -> Path:
    """Render the star-schema DDL for PostgreSQL to *out_path*.

    Args:
        out_path: Destination SQL file.

    Returns:
        The path written.
    """
    from sqlalchemy.dialects import postgresql

    dialect = postgresql.dialect()
    chunks = [
        "-- FabPulse warehouse DDL (PostgreSQL 15+). Generated from fabpulse.schema.",
        "-- The API auto-creates the same tables on SQLite when no server is available.",
        "",
    ]
    for table in ALL_TABLES:
        chunks.append(str(CreateTable(table).compile(dialect=dialect)).strip() + ";")
        for index in table.indexes:
            chunks.append(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";")
        chunks.append("")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(chunks), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI: write the Postgres DDL snapshot used by reviewers and DBAs."""
    parser = argparse.ArgumentParser(description="Write FabPulse Postgres DDL")
    parser.add_argument("--out", default="scripts/schema.sql", help="output SQL file")
    args = parser.parse_args(argv)
    path = write_postgres_ddl(args.out)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
