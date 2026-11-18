import { ArrowDownOutlined, ArrowUpOutlined, InfoCircleOutlined, MinusOutlined } from '@ant-design/icons'
import { Card, Statistic, Tooltip, Typography } from 'antd'
import type { ReactNode } from 'react'

export interface MetricTrend {
  direction: 'up' | 'down' | 'flat'
  good: boolean
  label: string
}

interface MetricStatCardProps {
  title: string
  value: number | string | null | undefined
  precision?: number
  suffix?: string
  prefix?: ReactNode
  trend?: MetricTrend
  definition?: string
  loading?: boolean
}

const TREND_ICON = {
  up: <ArrowUpOutlined />,
  down: <ArrowDownOutlined />,
  flat: <MinusOutlined />,
}

/**
 * KPI card with a plain-language tooltip. The arrow is green when the movement
 * is good for the business (for MTTR, lower is good) and red otherwise.
 */
export default function MetricStatCard({
  title,
  value,
  precision = 1,
  suffix,
  prefix,
  trend,
  definition,
  loading = false,
}: MetricStatCardProps) {
  const displayValue =
    value === null || value === undefined
      ? 'n/a'
      : typeof value === 'number'
        ? Number(value.toFixed(precision))
        : value

  return (
    <Card size="small" loading={loading} style={{ height: '100%' }}>
      <Tooltip title={definition}>
        <Typography.Text type="secondary" style={{ cursor: 'help' }}>
          {title} <InfoCircleOutlined style={{ fontSize: 11 }} />
        </Typography.Text>
      </Tooltip>
      <Statistic
        value={displayValue}
        precision={typeof displayValue === 'number' ? precision : undefined}
        suffix={suffix}
        prefix={prefix}
        valueStyle={{ fontSize: 24, fontWeight: 600 }}
      />
      {trend ? (
        <Typography.Text
          type={trend.good ? 'success' : 'danger'}
          style={{ fontSize: 12, whiteSpace: 'nowrap' }}
        >
          {TREND_ICON[trend.direction]} {trend.label}
        </Typography.Text>
      ) : (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          &nbsp;
        </Typography.Text>
      )}
    </Card>
  )
}
