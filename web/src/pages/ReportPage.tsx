import { useEffect } from 'react'
import {
  Card,
  Collapse,
  Col,
  Descriptions,
  Empty,
  Row,
  Skeleton,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { Excursion, ParetoRow, ShiftComparison } from '../api/types'
import { InlineError } from '../components/ChartCard'
import { useReport } from '../hooks/useData'
import { useFilterState } from '../hooks/useFilterState'

const excursionColumns: ColumnsType<Excursion> = [
  { title: '#', dataIndex: 'rank', width: 50 },
  {
    title: 'Tool',
    dataIndex: 'tool_id',
    width: 120,
    render: (value: string) => <Typography.Text strong>{value}</Typography.Text>,
  },
  {
    title: 'Metric',
    dataIndex: 'metric',
    width: 120,
    render: (value: string) =>
      ({
        throughput_wph: 'Throughput',
        yield_pct: 'Yield',
        wafers_processed: 'Wafers',
        availability_pct: 'Availability',
      })[value] ?? value,
  },
  {
    title: 'Severity',
    dataIndex: 'severity',
    width: 100,
    render: (value: string) => (
      <Tag color={value === 'CRITICAL' ? 'red' : value === 'HIGH' ? 'orange' : 'gold'}>{value}</Tag>
    ),
  },
  {
    title: 'Finding',
    dataIndex: 'headline',
    render: (value: string) => <span>{value}</span>,
  },
]

const paretoColumns: ColumnsType<ParetoRow> = [
  { title: 'Fault code', dataIndex: 'fault_code', width: 160 },
  { title: 'Category', dataIndex: 'fault_category', width: 140 },
  { title: 'Severity', dataIndex: 'severity', width: 100 },
  {
    title: 'Events',
    dataIndex: 'count',
    width: 90,
    render: (value: number) => value.toLocaleString(),
  },
  {
    title: '% of faults',
    dataIndex: 'pct_of_total',
    width: 110,
    render: (value: number) => `${value.toFixed(1)}%`,
  },
  {
    title: 'Cumulative',
    dataIndex: 'cumulative_pct',
    width: 110,
    render: (value: number) => `${value.toFixed(1)}%`,
  },
]

const shiftColumns: ColumnsType<ShiftComparison> = [
  { title: 'Tool', dataIndex: 'tool_id', width: 130 },
  {
    title: 'Handoff',
    key: 'handoff',
    width: 100,
    render: (_value, row) => `${row.from_shift} → ${row.to_shift}`,
  },
  {
    title: 'Δ',
    dataIndex: 'abs_delta',
    width: 100,
    render: (value: number) => `${value >= 0 ? '+' : ''}${value.toFixed(2)}`,
  },
  {
    title: 'Δ %',
    dataIndex: 'pct_delta',
    width: 90,
    render: (value: number | null) => (value === null ? 'n/a' : `${value.toFixed(1)}%`),
  },
  {
    title: 'Welch p',
    dataIndex: 'p_value',
    width: 120,
    render: (value: number | null) =>
      value === null ? 'n/a' : value < 0.001 ? 'p < 0.001' : `p = ${value.toFixed(3)}`,
  },
]

/** Plain-language engineer report: headline, ranked findings, drivers, glossary. */
export default function ReportPage() {
  const { filters } = useFilterState()
  const report = useReport(filters)

  useEffect(() => {
    document.title = 'FabPulse · Engineer report'
  }, [])

  if (report.error) {
    return <InlineError error={report.error} onRetry={report.reload} />
  }

  if (report.loading || !report.data) {
    return <Skeleton active paragraph={{ rows: 12 }} />
  }

  const data = report.data

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={3} style={{ marginBottom: 4 }}>
          Engineer report
        </Typography.Title>
        <Typography.Text type="secondary">
          Generated {new Date(data.generated_at).toLocaleString()} ·{' '}
          {data.date_range.min_date ?? 'n/a'} → {data.date_range.max_date ?? 'n/a'} ·{' '}
          {data.counts.events?.toLocaleString() ?? 0} event intervals
        </Typography.Text>
      </div>

      <Row gutter={[12, 12]}>
        {data.headline.map((item) => (
          <Col xs={12} sm={8} xl={4} key={item.label}>
            <Card
              size="small"
              title={<Typography.Text type="secondary">{item.label}</Typography.Text>}
            >
              <Statistic value={item.value} valueStyle={{ fontSize: 22 }} />
              <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                {item.detail}
              </Typography.Text>
            </Card>
          </Col>
        ))}
      </Row>

      <Card title="What the data says">
        {data.summary_sentences.map((sentence, index) => (
          <Typography.Paragraph key={index} style={{ fontSize: 15, lineHeight: 1.7 }}>
            {sentence}
          </Typography.Paragraph>
        ))}
      </Card>

      <Card title={`Top ${data.excursions.length} ranked excursions`}>
        {data.excursions.length ? (
          <Table<Excursion>
            rowKey={(row) => `${row.tool_id}-${row.metric}`}
            columns={excursionColumns}
            dataSource={data.excursions}
            pagination={false}
            scroll={{ x: 900 }}
          />
        ) : (
          <Empty description="No out-of-control or sustained-drift excursions in this window." />
        )}
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title={`Pareto 80% drivers (${data.pareto_drivers.length} codes)`}>
            <Table<ParetoRow>
              rowKey="fault_code"
              columns={paretoColumns}
              dataSource={data.pareto_drivers}
              pagination={false}
              size="small"
              scroll={{ x: 700 }}
            />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="Most significant shift-over-shift deltas">
            <Table<ShiftComparison>
              rowKey={(row) => `${row.tool_id}-${row.from_shift}-${row.to_shift}`}
              columns={shiftColumns}
              dataSource={data.shift_deltas}
              pagination={false}
              size="small"
              scroll={{ x: 640 }}
            />
          </Card>
        </Col>
      </Row>

      <Card title="Scope">
        <Descriptions
          size="small"
          column={{ xs: 1, sm: 2, lg: 4 }}
          items={[
            { key: 'tools', label: 'Tools', children: data.counts.tools ?? 0 },
            { key: 'days', label: 'Operational days', children: data.counts.days ?? 0 },
            {
              key: 'events',
              label: 'Events',
              children: (data.counts.events ?? 0).toLocaleString(),
            },
            {
              key: 'faults',
              label: 'Fault events',
              children: (data.counts.fault_events ?? 0).toLocaleString(),
            },
            {
              key: 'ooc',
              label: 'Out-of-control points',
              children: data.counts.out_of_control_points ?? 0,
            },
            {
              key: 'rules',
              label: 'Run-rule violations',
              children: data.counts.run_rule_violations ?? 0,
            },
          ]}
        />
      </Card>

      <Card title="Glossary">
        <Collapse
          items={data.glossary.map((entry) => ({
            key: entry.term,
            label: entry.term,
            children: <Typography.Paragraph>{entry.definition}</Typography.Paragraph>,
          }))}
        />
      </Card>
    </Space>
  )
}
