import type { ReactNode } from 'react'
import { Alert, Button, Card, Skeleton, Space } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'

interface ChartCardProps {
  title: ReactNode
  extra?: ReactNode
  loading?: boolean
  error?: Error | null
  onRetry?: () => void
  height?: number
  children: ReactNode
}

/** Card shell that owns the loading skeleton and error/retry state for a chart. */
export default function ChartCard({
  title,
  extra,
  loading = false,
  error = null,
  onRetry,
  height = 380,
  children,
}: ChartCardProps) {
  return (
    <Card
      title={title}
      extra={extra}
      style={{ height: '100%' }}
      styles={{ body: { minHeight: height } }}
    >
      {loading ? (
        <Skeleton active paragraph={{ rows: 8 }} />
      ) : error ? (
        <Alert
          type="error"
          showIcon
          message="Could not load this chart"
          description={error.message}
          action={
            onRetry ? (
              <Button size="small" icon={<ReloadOutlined />} onClick={onRetry}>
                Retry
              </Button>
            ) : undefined
          }
        />
      ) : (
        children
      )}
    </Card>
  )
}

export function InlineError({
  error,
  onRetry,
}: {
  error: Error
  onRetry?: () => void
}) {
  return (
    <Alert
      type="error"
      showIcon
      message="Request failed"
      description={error.message}
      action={
        onRetry ? (
          <Space>
            <Button size="small" icon={<ReloadOutlined />} onClick={onRetry}>
              Retry
            </Button>
          </Space>
        ) : undefined
      }
    />
  )
}
