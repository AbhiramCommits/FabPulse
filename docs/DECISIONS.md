# Architecture decisions

Five short ADRs recording the choices that shape FabPulse. Each lists the
context, the decision and the consequences we accept.

## ADR-001 — Use a star schema for the warehouse

**Context.** The raw log is a narrow event stream (timestamp, tool, shift,
state, fault, wafer counts, yield, duration). Analysts slice it by tool family,
site, shift, day and fault, and the same row feeds availability, Pareto and
drill-down queries.

**Decision.** Load a Kimball-style star schema: `fact_tool_event` at 5-minute
interval grain, with conformed `dim_tool`, `dim_date`, `dim_shift` and
`dim_fault` dimensions. Surrogate integer keys, no natural keys in the fact.
`recipe_id` is kept as a degenerate dimension because it is only useful in
drill-down, not as a join target.

**Consequences.** Filters and group-bys are simple joins on small dimensions;
dimensions can be extended (new fault categories, tool metadata) without
rewriting facts. The fact grain is fixed: per-interval metrics such as mean
yield must be aggregated, and adding lot-level analysis needs a new fact table.
The date dimension is operational-date based so the night shift does not split
across analytical days.

## ADR-002 — Push heavy aggregation into SQL, keep distribution math in pandas

**Context.** The warehouse holds ~310k facts. Availability needs grouped duration
sums, failure episodes need a window function, and the Pareto needs grouped
counts. Control limits, rolling statistics, percentiles and Welch tests are
easier to express and test in pandas/NumPy.

**Decision.** Put every heavy count/sum/group-mean and the `LAG`-based failure
episode detection in `fabpulse/queries.py` as SQLAlchemy Core text queries.
Keep rolling windows, SPC rules, percentiles, Tukey fences, Welch's t-test and
Pareto accumulation in `fabpulse/stats.py` with pandas/NumPy. Pure functions are
exported so known-array tests do not need a database.

**Consequences.** The database does what it is good at and transfers small
result sets; the statistical logic remains unit-testable without SQL. The SQL
must stay dialect-neutral for SQLite fallback, which rules out Postgres-only
percentile/window conveniences. Per-request aggregation is still costly on the
report endpoint; materialised daily aggregates are the planned next step.

## ADR-003 — Ant Design 5 + ECharts 5 for the console

**Context.** The console needs accessible tables, drawers, forms, responsive
grids, KPIs and statistical charts (control bands, heatmaps, box plots, dual
axes) without building a design system from scratch.

**Decision.** Use Ant Design for layout and components, and ECharts via
`echarts-for-react` for charts. Every chart is a thin wrapper over a pure
`buildOption(data, theme)` function. Theme tokens from AntD drive both the shell
and the chart palette.

**Consequences.** Fast delivery of a professional console, strong table/form
behaviour and responsive breakpoints. The bundle is large (AntD + full ECharts
≈ 2.27 MB, 725 kB gzip); route-level code splitting and ECharts tree shaking
are follow-ups. ECharts' canvas axis-label edge cases required snapping control
chart bounds to whole units and pinning `echarts-for-react@3.0.2`.

## ADR-004 — Encode filter state in the URL

**Context.** Engineers compare views and share findings. Filter state includes
dates, multiple tools, family, site, shifts and metric.

**Decision.** `useFilterState` serialises the complete filter object into the
query string on every change and parses it back on load. Views are shareable by
copying the URL; drill-down links carry the query string; the header has a
"Copy link" action. Defaults are omitted to keep URLs short.

**Consequences.** Reloads restore the exact view, browser back/forward works, and
no global store is needed. URLs can become long when many tools are selected;
we use comma-separated values and omit defaults. A future saved-view feature
can store the same string server-side.

## ADR-005 — Postgres-first SQL with a SQLite fallback

**Context.** The target warehouse is PostgreSQL 15+, but a reviewer may not have
a database server running. Requiring Postgres makes the project fragile to demo.

**Decision.** Write all DDL and analytical SQL for Postgres first, then keep it
dialect-neutral enough to run on SQLite. Configuration probes the Postgres URL
with a 2-second timeout; if it fails, the same SQLAlchemy Core code uses
`data/fabpulse.db`. Only connection arguments and timestamp tz-storage differ.

**Consequences.** `python data/generate.py && make ingest && make api` works on
a laptop with no server, and the full test suite runs on SQLite in CI without a
database service. The fallback lacks Postgres' type strictness, enforced foreign
keys (off by default), parallel query and concurrency; it is a development
convenience, not a production choice. The Postgres path remains the measured
and documented path.
