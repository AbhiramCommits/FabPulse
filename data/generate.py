#!/usr/bin/env python3
"""Generate a realistic, deliberately dirty raw equipment-log dataset.

The generator simulates twelve tools across three families (SCANNER, TRACK,
METRO), three eight-hour shifts per day, and five equipment states.  It writes
the same rows to CSV and Parquet so the ingestion layer can be tested for
format parity.

Injected signal (so the analytics have something real to find):

* Three tools with a gradual throughput decline across the window.
* A multi-day yield excursion on ``SCANNER-02``.
* A night-shift (C) throughput penalty and slightly more unscheduled downtime.
* Fault codes drawn from a 15-code long-tail distribution.
* ~0.5% dirty rows: null/garbage timestamps, negative durations, duplicate
  event ids, out-of-range yields and an unknown state value.

Usage:
    python data/generate.py --out data/raw
    python data/generate.py --out data/raw --days 14 --seed 7
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

FAMILIES = ("SCANNER", "TRACK", "METRO")
TOOLS_PER_FAMILY = 4
SHIFTS = ("A", "B", "C")
SHIFT_START_HOUR = {"A": 6, "B": 14, "C": 22}
SHIFT_THROUGHPUT_FACTOR = {"A": 1.02, "B": 1.00, "C": 0.94}
SHIFT_DOWN_RISK = {"A": 1.0, "B": 1.0, "C": 1.45}
STATES = (
    "PRODUCTIVE",
    "STANDBY",
    "SCHEDULED_DOWN",
    "UNSCHEDULED_DOWN",
    "ENGINEERING",
)
#: 15 fault codes with a deliberately long-tailed frequency distribution.
FAULTS: tuple[tuple[str, str, str, float], ...] = (
    ("VAC_LOSS", "Vacuum", "HIGH", 0.215),
    ("RF_REFLECT", "RF Power", "HIGH", 0.155),
    ("TEMP_DRIFT", "Thermal", "MEDIUM", 0.120),
    ("GAS_FLOW", "Gas Delivery", "HIGH", 0.100),
    ("CHUCK_CLAMP", "Wafer Handling", "MEDIUM", 0.080),
    ("LITHO_ALIGN", "Alignment", "HIGH", 0.070),
    ("SLIT_VALVE", "Vacuum", "CRITICAL", 0.055),
    ("ROBOT_PICK", "Wafer Handling", "CRITICAL", 0.040),
    ("PARTICLE", "Contamination", "MEDIUM", 0.035),
    ("CAL_DRIFT", "Calibration", "LOW", 0.028),
    ("PUMP_OVERHEAT", "Thermal", "HIGH", 0.022),
    ("EDGE_BEAD", "Coating", "LOW", 0.018),
    ("SENSOR_NOISE", "Instrumentation", "LOW", 0.015),
    ("LOADLOCK_LEAK", "Vacuum", "HIGH", 0.008),
    ("RECIPE_MISMATCH", "Software", "MEDIUM", 0.004),
)
FAULT_CODES = tuple(f[0] for f in FAULTS)
FAULT_WEIGHTS = np.array([f[3] for f in FAULTS], dtype=float)
FAULT_WEIGHTS /= FAULT_WEIGHTS.sum()

BASE_THROUGHPUT = {"SCANNER": 58.0, "TRACK": 44.0, "METRO": 31.0}
BASE_YIELD = {"SCANNER": 98.6, "TRACK": 98.2, "METRO": 99.1}
RECIPES = {
    "SCANNER": ("RCP-LITH-114", "RCP-LITH-207"),
    "TRACK": ("RCP-TRK-031", "RCP-TRK-058"),
    "METRO": ("RCP-MET-011", "RCP-MET-024"),
}
#: Tools with a gradual throughput decline and the fraction lost by day 90.
DEGRADED_TOOLS = {"SCANNER-03": 0.26, "TRACK-02": 0.20, "METRO-04": 0.15}
#: Yield excursion window (day indices) and magnitude on SCANNER-02.
YIELD_EXCURSION = {"tool": "SCANNER-02", "start_day": 62, "end_day": 70, "drop": 6.2}
#: A step-change throughput excursion on TRACK-04 (chamber fault, days 72-78).
THROUGHPUT_EXCURSION = {"tool": "TRACK-04", "start_day": 72, "end_day": 78, "drop": 0.30}
BAD_TIMESTAMP_SAMPLES = ("not-a-date", "", "2026-13-45T99:99:99Z")
DIRTY_FRACTION = 0.005


@dataclass(frozen=True)
class ToolSpec:
    """Static identity of a simulated tool."""

    tool_id: str
    tool_family: str
    fab_site: str
    base_throughput: float
    base_yield: float
    yield_offset: float
    degradation: float
    install_offset_days: int


def build_tools(tools_per_family: int = TOOLS_PER_FAMILY) -> list[ToolSpec]:
    """Build the deterministic tool roster (family, site and baseline rates)."""
    tools: list[ToolSpec] = []
    for family_index, family in enumerate(FAMILIES):
        for n in range(1, tools_per_family + 1):
            tool_id = f"{family}-{n:02d}"
            # Alternate sites inside each family so site filters are meaningful.
            site = "FAB-A" if n <= tools_per_family // 2 else "FAB-B"
            digest = int(hashlib.sha256(tool_id.encode()).hexdigest()[:8], 16)
            tools.append(
                ToolSpec(
                    tool_id=tool_id,
                    tool_family=family,
                    fab_site=site,
                    base_throughput=BASE_THROUGHPUT[family] * (0.94 + (digest % 100) / 830),
                    base_yield=BASE_YIELD[family] + ((digest >> 8) % 80 - 40) / 100,
                    yield_offset=((digest >> 4) % 70 - 35) / 100,
                    degradation=DEGRADED_TOOLS.get(tool_id, 0.0),
                    install_offset_days=200 + digest % 700 + family_index * 10,
                )
            )
    return tools


def _block(rng: np.random.Generator, length: int, low: int, high: int) -> tuple[int, int]:
    """Return a random (start, stop) interval block clipped to the day."""
    size = int(rng.integers(low, high + 1))
    start = int(rng.integers(0, max(1, length - size)))
    return start, min(length, start + size)


def simulate_day_states(
    rng: np.random.Generator,
    day_index: int,
    maintenance_period: int,
    maintenance_offset: int,
) -> np.ndarray:
    """Simulate the state of one tool for all 288 five-minute intervals of a day.

    Args:
        rng: Deterministic random generator.
        day_index: Zero-based day within the generated window.
        maintenance_period: Days between scheduled maintenance blocks.
        maintenance_offset: Phase offset of the maintenance cadence.

    Returns:
        An object array of length 288 holding state labels.
    """
    states = np.full(288, "PRODUCTIVE", dtype=object)

    # Scattered standby periods (~11% of intervals).
    states[rng.random(288) < 0.11] = "STANDBY"

    # Scheduled maintenance every N days, lasting 1-2 hours.
    if day_index % maintenance_period == maintenance_offset % maintenance_period:
        start, stop = _block(rng, 288, 12, 24)
        states[start:stop] = "SCHEDULED_DOWN"

    # Unscheduled failures: 0-2 episodes per day, weighted towards the night shift.
    n_failures = int(rng.poisson(0.30))
    for _ in range(n_failures):
        if rng.random() < 0.45:
            start = int(rng.integers(192, 270))
            stop = min(288, start + int(rng.integers(4, 16)))
        else:
            start, stop = _block(rng, 288, 4, 20)
        states[start:stop] = "UNSCHEDULED_DOWN"

    # Engineering / qualification runs: short, roughly every third day.
    if rng.random() < 0.34:
        start, stop = _block(rng, 288, 3, 12)
        states[start:stop] = "ENGINEERING"

    return states


def _day_factor(day_index: int, days: int, degradation: float) -> float:
    """Return the throughput multiplier for a tool on a given day."""
    if degradation <= 0:
        return 1.0
    progress = day_index / max(1, days - 1)
    return 1.0 - degradation * progress**1.25


def _yield_shape(day_index: int) -> float:
    """Return the excursion multiplier (0..1) for the yield-dip window."""
    spec = YIELD_EXCURSION
    if not (spec["start_day"] <= day_index <= spec["end_day"]):
        return 0.0
    span = max(1, spec["end_day"] - spec["start_day"])
    position = (day_index - spec["start_day"]) / span
    return float(np.sin(np.pi * position) ** 0.6)


def generate_events(
    days: int = 90,
    seed: int = 42,
    end_date: date | None = None,
    tools_per_family: int = TOOLS_PER_FAMILY,
    interval_s: int = 300,
) -> pd.DataFrame:
    """Generate the raw event log as a DataFrame.

    Args:
        days: Number of calendar days of history.
        seed: Seed for every random draw (fully deterministic).
        end_date: Last calendar day included (defaults to today, UTC).
        tools_per_family: Tools per equipment family.
        interval_s: Duration of each event interval in seconds.

    Returns:
        The raw event log including deliberately dirty rows.
    """
    if interval_s != 300:
        raise ValueError("only 300-second intervals are supported by the state simulator")
    if days < 1:
        raise ValueError("days must be positive")

    rng = np.random.default_rng(seed)
    tools = build_tools(tools_per_family)
    end = end_date or date.today()
    start = end - timedelta(days=days - 1)
    day_offsets = np.arange(days) * 86400
    intraday_offsets = SHIFT_START_HOUR["A"] * 3600 + np.arange(288) * interval_s
    absolute_offsets = (day_offsets[:, None] + intraday_offsets[None, :]).reshape(-1)
    timestamps = pd.Timestamp(start, tz="UTC") + pd.to_timedelta(absolute_offsets, unit="s")
    timestamp_strings = np.array(
        [ts.strftime("%Y-%m-%dT%H:%M:%SZ") for ts in timestamps], dtype=object
    )
    shift_labels = np.tile(np.repeat(np.array(SHIFTS, dtype=object), 96), days)

    frames: list[pd.DataFrame] = []
    for tool_index, tool in enumerate(tools):
        maintenance_period = 9 + (tool_index % 5)
        maintenance_offset = tool_index * 3

        state_chunks: list[np.ndarray] = []
        for day_index in range(days):
            state_chunks.append(
                simulate_day_states(rng, day_index, maintenance_period, maintenance_offset)
            )
        states = np.concatenate(state_chunks)

        productive = states == "PRODUCTIVE"
        non_productive = ~productive
        is_down = (states == "UNSCHEDULED_DOWN") | (states == "SCHEDULED_DOWN")

        # Per-day throughput trend, shift factor and lognormal-ish noise.
        trend = np.array(
            [_day_factor(d, days, tool.degradation) for d in range(days)], dtype=float
        )
        trend_per_interval = np.repeat(trend, 288)
        shift_modifier = np.where(
            shift_labels == "A", 1.02, np.where(shift_labels == "B", 1.00, 0.94)
        )
        noise = rng.normal(1.0, 0.035, size=len(states)).clip(0.75, 1.25)
        excursion_factor = np.ones(len(states))
        if tool.tool_id == THROUGHPUT_EXCURSION["tool"]:
            in_window = np.repeat(
                [
                    THROUGHPUT_EXCURSION["start_day"] <= d <= THROUGHPUT_EXCURSION["end_day"]
                    for d in range(days)
                ],
                288,
            )
            excursion_factor[in_window] = 1.0 - THROUGHPUT_EXCURSION["drop"]
        throughput = (
            tool.base_throughput
            * trend_per_interval
            * shift_modifier
            * noise
            * excursion_factor
            * productive
        ).round(2)
        wafers = np.round(throughput * interval_s / 3600).astype(int)
        wafers[non_productive] = 0

        # Yield only exists for productive intervals; the excursion is added.
        yield_values = np.full(len(states), np.nan)
        excursion = np.array(
            [_yield_shape(d) for d in range(days)], dtype=float
        ) if tool.tool_id == YIELD_EXCURSION["tool"] else np.zeros(days)
        excursion_per_interval = np.repeat(excursion, 288) * YIELD_EXCURSION["drop"]
        yield_values[productive] = (
            tool.base_yield
            + tool.yield_offset
            - excursion_per_interval[productive]
            + rng.normal(0, 0.42, size=productive.sum())
        ).clip(80.0, 99.95)

        # Fault codes: every down interval has one; engineering and productive
        # intervals occasionally carry a (less severe) code too.
        fault_codes = np.full(len(states), None, dtype=object)
        down_positions = np.flatnonzero(is_down)
        if len(down_positions):
            fault_codes[down_positions] = rng.choice(
                FAULT_CODES, size=len(down_positions), p=FAULT_WEIGHTS
            )
        engineering_positions = np.flatnonzero(states == "ENGINEERING")
        if len(engineering_positions):
            engineering_with_fault = rng.choice(
                engineering_positions,
                size=int(len(engineering_positions) * 0.25),
                replace=False,
            )
            fault_codes[engineering_with_fault] = rng.choice(
                ["RECIPE_MISMATCH", "CAL_DRIFT", "SENSOR_NOISE"],
                size=len(engineering_with_fault),
            )
        productive_positions = np.flatnonzero(productive)
        minor_positions = rng.choice(
            productive_positions, size=int(len(productive_positions) * 0.004), replace=False
        )
        fault_codes[minor_positions] = rng.choice(
            ["SENSOR_NOISE", "PARTICLE", "EDGE_BEAD"], size=len(minor_positions)
        )

        recipe_choices = RECIPES[tool.tool_family]
        recipes = np.array(recipe_choices, dtype=object)[
            rng.integers(0, len(recipe_choices), size=len(states))
        ]

        frames.append(
            pd.DataFrame(
                {
                    "timestamp": timestamp_strings.copy(),
                    "tool_id": tool.tool_id,
                    "tool_family": tool.tool_family,
                    "fab_site": tool.fab_site,
                    "shift": shift_labels.copy(),
                    "state": states,
                    "fault_code": fault_codes,
                    "wafers_processed": wafers.astype(np.int64),
                    "throughput_wph": throughput.astype(float),
                    "yield_pct": yield_values.astype(float),
                    "recipe_id": recipes,
                    "duration_s": np.full(len(states), interval_s, dtype=np.int64),
                }
            )
        )

    frame = pd.concat(frames, ignore_index=True)
    frame = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)
    frame.insert(0, "event_id", [f"EVT-{i:09d}" for i in range(len(frame))])
    frame = _inject_dirty_rows(frame, rng)
    return frame


def _inject_dirty_rows(frame: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Inject ~0.5% dirty rows across five distinct failure modes."""
    dirty_per_mode = max(5, int(round(len(frame) * DIRTY_FRACTION / 5)))
    total_dirty = dirty_per_mode * 5
    chosen = rng.permutation(len(frame))[:total_dirty]
    groups = np.array_split(chosen, 5)
    timestamp_pos = frame.columns.get_loc("timestamp")
    duration_pos = frame.columns.get_loc("duration_s")
    yield_pos = frame.columns.get_loc("yield_pct")
    state_pos = frame.columns.get_loc("state")

    # 1) Duplicate event ids: append verbatim copies (same event_id).
    duplicates = frame.iloc[groups[0]].copy()
    frame = pd.concat([frame, duplicates], ignore_index=True)

    # 2) Null or unparseable timestamps.
    null_positions = frame.index[groups[1]]
    bad_values: list[str | None] = [None] * (len(null_positions) // 2)
    bad_values += list(
        rng.choice(BAD_TIMESTAMP_SAMPLES, size=len(null_positions) - len(bad_values), replace=True)
    )
    frame.iloc[null_positions, timestamp_pos] = bad_values

    # 3) Negative durations.
    frame.iloc[frame.index[groups[2]], duration_pos] = -300

    # 4) Out-of-range yield.
    bad_yields = rng.choice([150.0, -12.5, 101.7], size=len(groups[3]))
    frame.iloc[frame.index[groups[3]], yield_pos] = bad_yields

    # 5) Unknown equipment state.
    frame.iloc[frame.index[groups[4]], state_pos] = "MAINTENANCE"

    parseable = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    order = parseable.sort_values(kind="stable", na_position="last").index
    frame = frame.loc[order].reset_index(drop=True)
    return frame


def _human_size(num_bytes: int) -> str:
    """Format a byte count for the CLI summary."""
    if num_bytes >= 1_048_576:
        return f"{num_bytes / 1_048_576:.2f} MB"
    return f"{num_bytes / 1024:.1f} KB"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: generate and write CSV + Parquet, then print a summary."""
    parser = argparse.ArgumentParser(description="Generate synthetic FabPulse equipment logs")
    parser.add_argument("--out", default="data/raw", help="output directory")
    parser.add_argument("--days", type=int, default=90, help="days of history")
    parser.add_argument("--seed", type=int, default=42, help="random seed")
    parser.add_argument(
        "--tools-per-family", type=int, default=TOOLS_PER_FAMILY, help="tools per family"
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="last calendar day (YYYY-MM-DD, default: today UTC)",
    )
    args = parser.parse_args(argv)

    end_date = date.fromisoformat(args.end_date) if args.end_date else None
    try:
        frame = generate_events(
            days=args.days,
            seed=args.seed,
            end_date=end_date,
            tools_per_family=args.tools_per_family,
        )
    except ValueError as exc:
        parser.error(str(exc))
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "equipment_events.csv"
    parquet_path = out_dir / "equipment_events.parquet"
    frame.to_csv(csv_path, index=False)
    frame.to_parquet(parquet_path, index=False, compression="snappy")

    parsed = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    start, stop = parsed.min(), parsed.max()
    dirty = (
        frame["timestamp"].isna()
        | (pd.to_datetime(frame["timestamp"], errors="coerce", utc=True).isna())
        | (frame["duration_s"] < 0)
        | (~frame["yield_pct"].isna() & ~frame["yield_pct"].between(0, 100))
        | (~frame["state"].isin(STATES))
        | frame["event_id"].duplicated(keep="first")
    ).sum()

    print("FabPulse synthetic equipment log")
    print(f"  rows            : {len(frame):,}")
    print(f"  date range (UTC): {start:%Y-%m-%d} .. {stop:%Y-%m-%d} ({args.days} days)")
    print(f"  tools           : {frame['tool_id'].nunique()} across {frame['tool_family'].nunique()} families")
    print(f"  shifts          : {', '.join(SHIFTS)}")
    print(f"  dirty rows      : {int(dirty):,} ({dirty / len(frame):.2%})")
    print(f"  csv             : {csv_path} ({_human_size(csv_path.stat().st_size)})")
    print(f"  parquet         : {parquet_path} ({_human_size(parquet_path.stat().st_size)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
