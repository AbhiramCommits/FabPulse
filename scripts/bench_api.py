#!/usr/bin/env python3
"""Measure FabPulse API latency over a loop of real HTTP requests.

Start the API first (``make api``), then:

    python scripts/bench_api.py --iterations 20

The script warms each endpoint, records wall-clock latency, and prints p50/p95/
max per endpoint plus an overall p95. It is deliberately dependency-light
(``httpx`` only) so the numbers in the README are easy to reproduce.
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
import time
from dataclasses import dataclass

import httpx

ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("health", "/api/health"),
    ("meta/filters", "/api/meta/filters"),
    ("kpis", "/api/kpis"),
    ("timeseries", "/api/timeseries?window=7&metric=throughput_wph"),
    ("boxplot", "/api/boxplot?metric=yield_pct"),
    ("pareto", "/api/pareto"),
    ("heatmap", "/api/heatmap"),
    ("shifts/delta", "/api/shifts/delta?metric=throughput_wph"),
    ("events page", "/api/tools/SCANNER-02/events?page=1&page_size=25"),
    ("report/summary", "/api/report/summary"),
)


@dataclass
class Result:
    """Latency samples for one endpoint."""

    label: str
    path: str
    samples: list[float]

    def percentile(self, fraction: float) -> float:
        """Return the nearest-rank percentile in milliseconds."""
        ordered = sorted(self.samples)
        index = max(0, math.ceil(fraction * len(ordered)) - 1)
        return ordered[index] * 1000.0

    @property
    def p50(self) -> float:
        """Median latency in milliseconds."""
        return statistics.median(self.samples) * 1000.0

    @property
    def p95(self) -> float:
        """95th-percentile latency in milliseconds."""
        return self.percentile(0.95)

    @property
    def maximum(self) -> float:
        """Maximum latency in milliseconds."""
        return max(self.samples) * 1000.0


def run_benchmark(base_url: str, iterations: int, warmup: int = 2) -> list[Result]:
    """Benchmark every endpoint and return the latency results.

    Args:
        base_url: API root, e.g. ``http://127.0.0.1:8000``.
        iterations: Timed requests per endpoint.
        warmup: Untimed warm-up requests per endpoint.

    Returns:
        One :class:`Result` per endpoint.
    """
    results: list[Result] = []
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        for label, path in ENDPOINTS:
            for _ in range(warmup):
                response = client.get(path)
                response.raise_for_status()
            samples: list[float] = []
            for _ in range(iterations):
                started = time.perf_counter()
                response = client.get(path)
                elapsed = time.perf_counter() - started
                response.raise_for_status()
                samples.append(elapsed)
            results.append(Result(label=label, path=path, samples=samples))
    return results


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: run the benchmark and print a latency table."""
    parser = argparse.ArgumentParser(description="Benchmark the FabPulse API")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args(argv)

    try:
        results = run_benchmark(args.base_url, max(1, args.iterations))
    except (httpx.HTTPError, OSError) as exc:
        print(f"benchmark failed: {exc}", file=sys.stderr)
        return 1

    print(f"FabPulse API latency · {args.iterations} timed requests per endpoint")
    print(f"{'endpoint':<20} {'n':>3} {'p50 ms':>9} {'p95 ms':>9} {'max ms':>9}")
    print("-" * 55)
    all_samples: list[float] = []
    for result in results:
        all_samples.extend(result.samples)
        print(
            f"{result.label:<20} {len(result.samples):>3} "
            f"{result.p50:>9.1f} {result.p95:>9.1f} {result.maximum:>9.1f}"
        )
    overall = Result(label="overall", path="", samples=all_samples)
    print("-" * 55)
    print(
        f"{'overall':<20} {len(all_samples):>3} "
        f"{overall.p50:>9.1f} {overall.p95:>9.1f} {overall.maximum:>9.1f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
