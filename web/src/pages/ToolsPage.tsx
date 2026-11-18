import { useEffect, useMemo, useState } from 'react'
import { Alert, Card, Space, Table, Tag, Tooltip, Typography } from 'antd'
import type { ColumnsType, TableProps } from 'antd/es/table'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import type { ToolKpi } from '../api/types'
import ChartCard from '../components/ChartCard'
import { ExcursionBoxPlot } from '../charts'
import { useBoxplot, useKpis, useMeta } from '../hooks/useData'
import { filtersKey, useFilterState } from '../hooks/useFilterState'

function fmt(value: number | null | undefined, digits = 1, suffix = ''): string {
  if (value === null || value === undefined) return 'n/a'
  return `${value.toFixed(digits)}${suffix}`
}

/** Per-tool KPI table with server-side paging/sorting/filtering plus box plots. */
export default function ToolsPage() {
  const { filters, setFilters } = useFilterState()
  const meta = useMeta()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [sortBy, setSortBy] = useState('tool_id')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const kpis = useKpis(filters, page, pageSize, sortBy, sortDir)
  const boxplot = useBoxplot(filters)
  const navigate = useNavigate()
  const location = useLocation()
  const filterSignature = filtersKey(filters)

  useEffect(() => {
    setPage(1)
  }, [filterSignature])

  useEffect(() => {
    document.title = 'FabPulse · Tools'
  }, [])

  const columns = useMemo<ColumnsType<ToolKpi>>(
    () => [
      {
        title: 'Tool',
        dataIndex: 'tool_id',
        key: 'tool_id',
        fixed: 'left',
        width: 150,
        sorter: true,
        filters: (meta.data?.tools ?? []).map((tool) => ({
          text: tool.tool_id,
          value: tool.tool_id,
        })),
        filteredValue: filters.tool_ids.length ? filters.tool_ids : null,
        render: (value: string) => <Link to={`/tools/${value}${location.search}`}>{value}</Link>,
      },
      {
        title: 'Family',
        dataIndex: 'tool_family',
        key: 'tool_family',
        width: 120,
        sorter: true,
        filters: (meta.data?.families ?? []).map((family) => ({
          text: family,
          value: family,
        })),
        filteredValue: filters.tool_family ? [filters.tool_family] : null,
        render: (value: string) => <Tag>{value}</Tag>,
      },
      {
        title: 'Site',
        dataIndex: 'fab_site',
        key: 'fab_site',
        width: 96,
        sorter: true,
        filters: (meta.data?.sites ?? []).map((site) => ({ text: site, value: site })),
        filteredValue: filters.fab_site ? [filters.fab_site] : null,
      },
      {
        title: 'Uptime',
        dataIndex: 'uptime_pct',
        key: 'uptime_pct',
        width: 112,
        sorter: true,
        render: (value: number | null) => fmt(value, 1, '%'),
      },
      {
        title: 'Availability',
        dataIndex: 'availability_pct',
        key: 'availability_pct',
        width: 130,
        sorter: true,
        render: (value: number | null) => fmt(value, 1, '%'),
      },
      {
        title: 'MTBF',
        dataIndex: 'mtbf_hours',
        key: 'mtbf_hours',
        width: 104,
        sorter: true,
        render: (value: number | null) => fmt(value, 1, ' h'),
      },
      {
        title: 'MTTR',
        dataIndex: 'mttr_hours',
        key: 'mttr_hours',
        width: 104,
        sorter: true,
        render: (value: number | null) => fmt(value, 2, ' h'),
      },
      {
        title: 'Throughput',
        dataIndex: 'avg_throughput_wph',
        key: 'avg_throughput_wph',
        width: 136,
        sorter: true,
        render: (value: number | null) => fmt(value, 1, ' wph'),
      },
      {
        title: 'Yield',
        dataIndex: 'avg_yield_pct',
        key: 'avg_yield_pct',
        width: 112,
        sorter: true,
        render: (value: number | null) => fmt(value, 2, '%'),
      },
      {
        title: 'Failures',
        dataIndex: 'failure_episodes',
        key: 'failure_episodes',
        width: 108,
        sorter: true,
      },
      {
        title: 'Wafers',
        dataIndex: 'wafers',
        key: 'wafers',
        width: 112,
        sorter: true,
        render: (value: number) => value.toLocaleString(),
      },
    ],
    [filters.fab_site, filters.tool_family, filters.tool_ids, location.search, meta.data],
  )

  const onChange: TableProps<ToolKpi>['onChange'] = (pagination, tableFilters, sorter, extra) => {
    setPage(pagination.current ?? 1)
    setPageSize(pagination.pageSize ?? 10)
    const activeSorter = Array.isArray(sorter) ? sorter[0] : sorter
    if (activeSorter?.order && activeSorter.field) {
      setSortBy(String(activeSorter.field))
      setSortDir(activeSorter.order === 'ascend' ? 'asc' : 'desc')
      setPage(1)
    }
    if (extra.action === 'filter') {
      setFilters({
        tool_ids: (tableFilters.tool_id as string[] | null) ?? [],
        tool_family: ((tableFilters.tool_family as string[] | null) ?? [])[0] ?? null,
        fab_site: ((tableFilters.fab_site as string[] | null) ?? [])[0] ?? null,
      })
    }
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={3} style={{ marginBottom: 4 }}>
          Tool fleet
        </Typography.Title>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
          Sort any column, use the column filters, or click a row to drill into the tool
          timeline. Paging, sorting and filtering all run on the API.
        </Typography.Paragraph>
      </div>

      {kpis.error ? (
        <Alert type="error" showIcon message="Could not load tool KPIs" description={kpis.error.message} />
      ) : (
        <Table<ToolKpi>
          rowKey="tool_id"
          loading={kpis.loading}
          columns={columns}
          dataSource={kpis.data?.tools ?? []}
          onChange={onChange}
          scroll={{ x: 1290 }}
          onRow={(record) => ({
            onClick: () => navigate(`/tools/${record.tool_id}${location.search}`),
            style: { cursor: 'pointer' },
          })}
          pagination={{
            current: page,
            pageSize,
            total: kpis.data?.tools_total ?? 0,
            showSizeChanger: true,
            pageSizeOptions: [10, 25, 50],
            showTotal: (total) => `${total} tools`,
          }}
        />
      )}

      <ChartCard
        title={
          <Space>
            Daily distribution by tool
            <Tooltip title="Box = IQR, line = median, dots = Tukey outliers beyond 1.5×IQR">
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                (IQR + Tukey outliers)
              </Typography.Text>
            </Tooltip>
          </Space>
        }
        loading={boxplot.loading}
        error={boxplot.error}
        onRetry={boxplot.reload}
        height={380}
      >
        {boxplot.data ? <ExcursionBoxPlot data={boxplot.data} /> : null}
      </ChartCard>

      <Card size="small">
        <Typography.Text type="secondary">
          {boxplot.data
            ? `${boxplot.data.total_outliers} Tukey outliers across ${boxplot.data.tools.length} tools for ${boxplot.data.metric.replace('_', ' ')}.`
            : 'Loading distribution summary…'}
        </Typography.Text>
      </Card>
    </Space>
  )
}
