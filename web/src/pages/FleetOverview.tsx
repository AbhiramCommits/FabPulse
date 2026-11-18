import { useEffect, useMemo, useState } from 'react'
import { Col, Grid, Row, Segmented, Space, Typography } from 'antd'
import type { MetricTrend } from '../components/MetricStatCard'
import MetricStatCard from '../components/MetricStatCard'
import ChartCard from '../components/ChartCard'
import { METRIC_DEFINITIONS } from '../constants/metricDefinitions'
import { TrendChart, FaultHeatmap, FaultPareto, metricLabel } from '../charts'
import type { HeatmapMode } from '../charts'
import { useKpis, useTimeseries, usePareto, useHeatmap } from '../hooks/useData'
import { useFilterState } from '../hooks/useFilterState'
import type { FilterState, TimeSeriesResponse } from '../api/types'

function mean(values: number[]): number | null {
  if (!values.length) return null
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function seriesTrend(
  data: TimeSeriesResponse | null,
  lowerIsBetter = false,
): MetricTrend | undefined {
  if (!data) return undefined
  const values = data.series
    .map((point) => point.value)
    .filter((value): value is number => value !== null && Number.isFinite(value))
  if (values.length < 8) return undefined
  const recent = mean(values.slice(-7))
  const prior = mean(values.slice(-14, -7))
  if (recent === null || prior === null || prior === 0) return undefined
  const pct = ((recent - prior) / prior) * 100
  const direction = pct > 0.2 ? 'up' : pct < -0.2 ? 'down' : 'flat'
  const good = lowerIsBetter ? direction !== 'up' : direction !== 'down'
  return {
    direction,
    good,
    label: `${Math.abs(pct).toFixed(1)}% vs prior 7 days`,
  }
}

function targetTrend(
  value: number | null | undefined,
  target: number,
  higherIsBetter = true,
): MetricTrend | undefined {
  if (value === null || value === undefined) return undefined
  const above = value >= target
  const direction = above ? 'up' : 'down'
  return {
    direction,
    good: higherIsBetter ? above : !above,
    label: `vs ${target} target`,
  }
}

/** Fleet overview: KPI cards, control chart, Pareto and interactive heatmap. */
export default function FleetOverview() {
  const { filters, setFilters } = useFilterState()
  const kpis = useKpis(filters, 1, 12)
  const series = useTimeseries(filters, 7, 3)
  const pareto = usePareto(filters)
  const heatmap = useHeatmap(filters)
  const throughputSeries = useTimeseries(
    useMemo<FilterState>(() => ({ ...filters, metric: 'throughput_wph' }), [filters]),
    7,
    3,
  )
  const yieldSeries = useTimeseries(
    useMemo<FilterState>(() => ({ ...filters, metric: 'yield_pct' }), [filters]),
    7,
    3,
  )
  const [heatmapMode, setHeatmapMode] = useState<HeatmapMode>('shift')
  const screens = Grid.useBreakpoint()

  useEffect(() => {
    document.title = 'FabPulse · Fleet overview'
  }, [])

  const fleet = kpis.data?.fleet

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={3} style={{ marginBottom: 4 }}>
          Fleet overview
        </Typography.Title>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
          {fleet
            ? `${fleet.tool_count} tools · ${fleet.events.toLocaleString()} event intervals · ${fleet.wafers.toLocaleString()} wafers in scope`
            : 'Loading equipment telemetry…'}
        </Typography.Paragraph>
      </div>

      <Row gutter={[12, 12]}>
        <Col xs={12} sm={8} xl={4}>
          <MetricStatCard
            title="Uptime"
            value={fleet?.uptime_pct}
            suffix="%"
            loading={kpis.loading}
            definition={METRIC_DEFINITIONS.uptime_pct}
            trend={targetTrend(fleet?.uptime_pct, 85)}
          />
        </Col>
        <Col xs={12} sm={8} xl={4}>
          <MetricStatCard
            title="Availability (OEE)"
            value={fleet?.availability_pct}
            suffix="%"
            loading={kpis.loading}
            definition={METRIC_DEFINITIONS.availability_pct}
            trend={targetTrend(fleet?.availability_pct, 85)}
          />
        </Col>
        <Col xs={12} sm={8} xl={4}>
          <MetricStatCard
            title="MTBF"
            value={fleet?.mtbf_hours}
            suffix=" h"
            loading={kpis.loading}
            definition={METRIC_DEFINITIONS.mtbf_hours}
            trend={targetTrend(fleet?.mtbf_hours, 48)}
          />
        </Col>
        <Col xs={12} sm={8} xl={4}>
          <MetricStatCard
            title="MTTR"
            value={fleet?.mttr_hours}
            precision={2}
            suffix=" h"
            loading={kpis.loading}
            definition={METRIC_DEFINITIONS.mttr_hours}
            trend={targetTrend(fleet?.mttr_hours, 2, false)}
          />
        </Col>
        <Col xs={12} sm={8} xl={4}>
          <MetricStatCard
            title="Throughput p50"
            value={fleet?.throughput_p50}
            suffix=" wph"
            loading={kpis.loading}
            definition={METRIC_DEFINITIONS.throughput}
            trend={seriesTrend(throughputSeries.data)}
          />
        </Col>
        <Col xs={12} sm={8} xl={4}>
          <MetricStatCard
            title="Yield"
            value={fleet?.avg_yield_pct}
            precision={2}
            suffix="%"
            loading={kpis.loading}
            definition={METRIC_DEFINITIONS.yield_pct}
            trend={seriesTrend(yieldSeries.data)}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={15}>
          <ChartCard
            title={`${metricLabel(filters.metric)} control chart`}
            extra={
              screens.sm ? (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  7d rolling · 3σ limits · brush to zoom
                </Typography.Text>
              ) : null
            }
            loading={series.loading}
            error={series.error}
            onRetry={series.reload}
            height={380}
          >
            {series.data ? (
              <TrendChart
                data={series.data}
                onBrush={([from, to]) => setFilters({ from_date: from, to_date: to })}
              />
            ) : null}
          </ChartCard>
        </Col>
        <Col xs={24} xl={9}>
          <ChartCard
            title="Fault Pareto"
            extra={
              pareto.data ? (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {pareto.data.codes_for_80.length} of {pareto.data.n_codes} codes = 80%
                </Typography.Text>
              ) : null
            }
            loading={pareto.loading}
            error={pareto.error}
            onRetry={pareto.reload}
            height={380}
          >
            {pareto.data ? <FaultPareto data={pareto.data} /> : null}
          </ChartCard>
        </Col>
      </Row>

      <ChartCard
        title="Fault heatmap"
        extra={
          <Segmented
            value={heatmapMode}
            onChange={(value) => setHeatmapMode(value as HeatmapMode)}
            options={[
              { label: 'Tool × shift', value: 'shift' },
              { label: 'Tool × fault', value: 'fault' },
            ]}
          />
        }
        loading={heatmap.loading}
        error={heatmap.error}
        onRetry={heatmap.reload}
        height={420}
      >
        {heatmap.data ? <FaultHeatmap data={heatmap.data} mode={heatmapMode} /> : null}
      </ChartCard>
    </Space>
  )
}
