import { useEffect, useMemo, useState } from 'react'
import { Alert, Card, Col, Result, Row, Space, Statistic, Table, Tag, Typography } from 'antd'
import type { ColumnsType, TableProps } from 'antd/es/table'
import { Link, useParams } from 'react-router-dom'
import dayjs from 'dayjs'
import type { EventRow, ShiftComparison } from '../api/types'
import ChartCard from '../components/ChartCard'
import MetricStatCard from '../components/MetricStatCard'
import StateTag from '../components/StateTag'
import { TrendChart, metricLabel } from '../charts'
import { METRIC_DEFINITIONS } from '../constants/metricDefinitions'
import { useKpis, useShiftDeltas, useTimeseries, useToolEvents } from '../hooks/useData'
import { filtersKey, useFilterState } from '../hooks/useFilterState'

function fmtP(pValue: number | null): string {
  if (pValue === null) return 'n/a'
  return pValue < 0.001 ? 'p < 0.001' : `p = ${pValue.toFixed(3)}`
}

function fmt(value: number | null | undefined, digits = 1, suffix = ''): string {
  if (value === null || value === undefined) return 'n/a'
  return `${value.toFixed(digits)}${suffix}`
}

const SHIFT_LABELS: Record<string, string> = {
  A: 'A · days',
  B: 'B · swings',
  C: 'C · nights',
}

/** Single-tool drill-down: KPIs, control chart, shift deltas and event timeline. */
export default function ToolDetailPage() {
  const { toolId = '' } = useParams<{ toolId: string }>()
  const { filters, setFilters } = useFilterState()
  const toolFilters = useMemo(() => ({ ...filters, tool_ids: [toolId] }), [filters, toolId])
  const kpis = useKpis(toolFilters, 1, 50)
  const series = useTimeseries(toolFilters, 7, 3)
  const shifts = useShiftDeltas(toolFilters)
  const [eventPage, setEventPage] = useState(1)
  const [eventPageSize, setEventPageSize] = useState(10)
  const [eventSortBy, setEventSortBy] = useState('ts')
  const [eventSortDir, setEventSortDir] = useState<'asc' | 'desc'>('desc')
  const events = useToolEvents(toolId, filters, eventPage, eventPageSize, eventSortBy, eventSortDir)
  const signature = filtersKey(filters)

  useEffect(() => {
    setEventPage(1)
  }, [signature])

  useEffect(() => {
    document.title = `FabPulse · ${toolId}`
  }, [toolId])

  const tool = kpis.data?.tools.find((item) => item.tool_id === toolId)
  const shiftSummary = shifts.data?.tools.find((item) => item.tool_id === toolId)

  const eventColumns = useMemo<ColumnsType<EventRow>>(
    () => [
      {
        title: 'Timestamp (UTC)',
        dataIndex: 'ts',
        key: 'ts',
        width: 150,
        sorter: true,
        defaultSortOrder: 'descend',
        render: (value: string) => dayjs(value).format('MMM D, HH:mm'),
      },
      {
        title: 'State',
        dataIndex: 'state',
        key: 'state',
        width: 150,
        render: (value: string) => <StateTag state={value} />,
      },
      {
        title: 'Fault',
        dataIndex: 'fault_code',
        key: 'fault_code',
        width: 140,
        render: (value: string | null) => (value ? <Tag color="volcano">{value}</Tag> : '—'),
      },
      { title: 'Shift', dataIndex: 'shift', key: 'shift', width: 70 },
      {
        title: 'Wafers',
        dataIndex: 'wafers_processed',
        key: 'wafers_processed',
        width: 86,
        sorter: true,
      },
      {
        title: 'Throughput',
        dataIndex: 'throughput_wph',
        key: 'throughput_wph',
        width: 110,
        sorter: true,
        render: (value: number) => `${value.toFixed(1)} wph`,
      },
      {
        title: 'Yield',
        dataIndex: 'yield_pct',
        key: 'yield_pct',
        width: 86,
        sorter: true,
        render: (value: number | null) => fmt(value, 2, '%'),
      },
      { title: 'Recipe', dataIndex: 'recipe_id', key: 'recipe_id', width: 130 },
    ],
    [],
  )

  const onEventChange: TableProps<EventRow>['onChange'] = (pagination, _tableFilters, sorter) => {
    setEventPage(pagination.current ?? 1)
    setEventPageSize(pagination.pageSize ?? 10)
    const activeSorter = Array.isArray(sorter) ? sorter[0] : sorter
    if (activeSorter?.order && activeSorter.field) {
      setEventSortBy(String(activeSorter.field))
      setEventSortDir(activeSorter.order === 'ascend' ? 'asc' : 'desc')
      setEventPage(1)
    }
  }

  const shiftColumns: ColumnsType<ShiftComparison> = [
    {
      title: 'Handoff',
      key: 'handoff',
      render: (_value, row) => `${row.from_shift} → ${row.to_shift}`,
    },
    {
      title: 'From mean',
      dataIndex: 'from_mean',
      key: 'from_mean',
      render: (value: number) => value.toFixed(2),
    },
    {
      title: 'To mean',
      dataIndex: 'to_mean',
      key: 'to_mean',
      render: (value: number) => value.toFixed(2),
    },
    {
      title: 'Δ',
      dataIndex: 'abs_delta',
      key: 'abs_delta',
      render: (value: number) => (
        <Typography.Text type={value >= 0 ? 'success' : 'danger'}>
          {value >= 0 ? '+' : ''}
          {value.toFixed(2)}
        </Typography.Text>
      ),
    },
    {
      title: 'Δ %',
      dataIndex: 'pct_delta',
      key: 'pct_delta',
      render: (value: number | null) => (value === null ? 'n/a' : `${value.toFixed(1)}%`),
    },
    {
      title: 'Welch p',
      dataIndex: 'p_value',
      key: 'p_value',
      render: (value: number | null) => fmtP(value),
    },
    {
      title: 'Verdict',
      key: 'significant',
      render: (_value, row) =>
        row.significant ? <Tag color="red">significant</Tag> : <Tag>not significant</Tag>,
    },
  ]

  if (!kpis.loading && kpis.data && !tool) {
    return (
      <Result
        status="404"
        title={`Tool ${toolId} not found`}
        subTitle="The tool may be outside the current filters, or the id is misspelled."
        extra={<Link to={`/tools${window.location.search}`}>Back to tools</Link>}
      />
    )
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Space align="center" wrap>
          <Typography.Title level={3} style={{ margin: 0 }}>
            {toolId}
          </Typography.Title>
          {tool ? <Tag color="geekblue">{tool.tool_family}</Tag> : null}
          {tool ? <Tag>{tool.fab_site}</Tag> : null}
          <Typography.Text type="secondary">
            {filters.from_date ?? series.data?.series[0]?.date ?? 'first day'} →{' '}
            {filters.to_date ?? series.data?.series.at(-1)?.date ?? 'last day'}
          </Typography.Text>
        </Space>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 0, marginTop: 6 }}>
          Tool-level control limits, handoff deltas and the raw 5-minute event timeline.
        </Typography.Paragraph>
      </div>

      <Row gutter={[12, 12]}>
        <Col xs={12} sm={8} xl={4}>
          <MetricStatCard
            title="Uptime"
            value={tool?.uptime_pct}
            suffix="%"
            loading={kpis.loading}
            definition={METRIC_DEFINITIONS.uptime_pct}
          />
        </Col>
        <Col xs={12} sm={8} xl={4}>
          <MetricStatCard
            title="Availability"
            value={tool?.availability_pct}
            suffix="%"
            loading={kpis.loading}
            definition={METRIC_DEFINITIONS.availability_pct}
          />
        </Col>
        <Col xs={12} sm={8} xl={4}>
          <MetricStatCard
            title="MTBF"
            value={tool?.mtbf_hours}
            suffix=" h"
            loading={kpis.loading}
            definition={METRIC_DEFINITIONS.mtbf_hours}
          />
        </Col>
        <Col xs={12} sm={8} xl={4}>
          <MetricStatCard
            title="MTTR"
            value={tool?.mttr_hours}
            precision={2}
            suffix=" h"
            loading={kpis.loading}
            definition={METRIC_DEFINITIONS.mttr_hours}
          />
        </Col>
        <Col xs={12} sm={8} xl={4}>
          <MetricStatCard
            title="Throughput"
            value={tool?.avg_throughput_wph}
            suffix=" wph"
            loading={kpis.loading}
            definition={METRIC_DEFINITIONS.throughput}
          />
        </Col>
        <Col xs={12} sm={8} xl={4}>
          <MetricStatCard
            title="Yield"
            value={tool?.avg_yield_pct}
            precision={2}
            suffix="%"
            loading={kpis.loading}
            definition={METRIC_DEFINITIONS.yield_pct}
          />
        </Col>
      </Row>

      {kpis.error ? (
        <Alert
          type="error"
          showIcon
          message="Could not load tool KPIs"
          description={kpis.error.message}
        />
      ) : null}

      <ChartCard
        title={`${metricLabel(filters.metric)} control chart · ${toolId}`}
        extra={
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {series.data
              ? `${series.data.out_of_control.length} out-of-control · ${series.data.violations.length} run-rule flags`
              : null}
          </Typography.Text>
        }
        loading={series.loading}
        error={series.error}
        onRetry={series.reload}
        height={360}
      >
        {series.data ? (
          <TrendChart
            data={series.data}
            height={360}
            onBrush={([from, to]) => setFilters({ from_date: from, to_date: to })}
          />
        ) : null}
      </ChartCard>

      <Row gutter={[16, 16]}>
        <Col xs={24}>
          <Card title="Shift-over-shift deltas" size="small" style={{ height: '100%' }}>
            <Row gutter={8}>
              {['A', 'B', 'C'].map((code) => (
                <Col span={8} key={code}>
                  <Statistic
                    title={SHIFT_LABELS[code]}
                    value={
                      shiftSummary?.shifts[code]?.mean == null
                        ? 'n/a'
                        : Number(shiftSummary.shifts[code].mean?.toFixed(2))
                    }
                    precision={2}
                    valueStyle={{ fontSize: 18 }}
                  />
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                    n={shiftSummary?.shifts[code]?.n ?? 0}
                  </Typography.Text>
                </Col>
              ))}
            </Row>
            <Table<ShiftComparison>
              style={{ marginTop: 12 }}
              size="small"
              rowKey={(row) => `${row.from_shift}-${row.to_shift}`}
              loading={shifts.loading}
              columns={shiftColumns}
              dataSource={shiftSummary?.comparisons ?? []}
              pagination={false}
              scroll={{ x: 640 }}
            />
          </Card>
        </Col>
        <Col xs={24}>
          <Card
            title="Recent event timeline"
            size="small"
            extra={
              events.data ? (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {events.data.total.toLocaleString()} intervals
                </Typography.Text>
              ) : null
            }
            styles={{ body: { padding: 0 } }}
          >
            <Table<EventRow>
              rowKey="event_key"
              size="small"
              loading={events.loading}
              columns={eventColumns}
              dataSource={events.data?.rows ?? []}
              onChange={onEventChange}
              scroll={{ x: 980 }}
              pagination={{
                current: eventPage,
                pageSize: eventPageSize,
                total: events.data?.total ?? 0,
                showSizeChanger: true,
                pageSizeOptions: [10, 25, 50],
                showTotal: (total) => `${total.toLocaleString()} events`,
              }}
            />
          </Card>
        </Col>
      </Row>
    </Space>
  )
}
