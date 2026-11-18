import { useEffect } from 'react'
import {
  Button,
  Checkbox,
  DatePicker,
  Divider,
  Drawer,
  Form,
  Radio,
  Select,
  Space,
  Typography,
} from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import type { FilterOptionsResponse, FilterState, Metric, ShiftCode } from '../api/types'

const { RangePicker } = DatePicker

export interface FilterFormValues {
  range?: [Dayjs | null, Dayjs | null] | null
  tool_ids?: string[]
  tool_family?: string | null
  fab_site?: string | null
  shifts?: ShiftCode[]
  metric: Metric
}

interface FilterDrawerProps {
  open: boolean
  onClose: () => void
  filters: FilterState
  meta: FilterOptionsResponse | null
  onApply: (values: FilterFormValues) => void
  onReset: () => void
}

const METRIC_OPTIONS: Array<{ label: string; value: Metric }> = [
  { label: 'Throughput (wph)', value: 'throughput_wph' },
  { label: 'Yield (%)', value: 'yield_pct' },
  { label: 'Wafers processed', value: 'wafers_processed' },
  { label: 'Availability (%)', value: 'availability_pct' },
]

const SHIFT_OPTIONS = [
  { label: 'A · 06:00–14:00', value: 'A' },
  { label: 'B · 14:00–22:00', value: 'B' },
  { label: 'C · 22:00–06:00', value: 'C' },
]

/** Global filter form. Every value lands in the URL, not local component state. */
export default function FilterDrawer({
  open,
  onClose,
  filters,
  meta,
  onApply,
  onReset,
}: FilterDrawerProps) {
  const [form] = Form.useForm<FilterFormValues>()

  useEffect(() => {
    if (!open) return
    form.setFieldsValue({
      range:
        filters.from_date && filters.to_date
          ? [dayjs(filters.from_date), dayjs(filters.to_date)]
          : null,
      tool_ids: filters.tool_ids,
      tool_family: filters.tool_family,
      fab_site: filters.fab_site,
      shifts: filters.shifts,
      metric: filters.metric,
    })
  }, [filters, form, open])

  const handleFinish = (values: FilterFormValues) => {
    onApply(values)
    onClose()
  }

  const handleReset = () => {
    form.resetFields()
    onReset()
    onClose()
  }

  return (
    <Drawer title="Filter telemetry" open={open} onClose={onClose} width="min(420px, 100vw)" destroyOnClose={false}>
      <Form<FilterFormValues>
        form={form}
        layout="vertical"
        onFinish={handleFinish}
        initialValues={{ metric: filters.metric, shifts: [], tool_ids: [] }}
      >
        <Form.Item label="Date range (operational days)" name="range">
          <RangePicker
            style={{ width: '100%' }}
            allowEmpty={[true, true]}
            disabledDate={(current) =>
              Boolean(meta?.date_bounds.max_date) &&
              current.isAfter(dayjs(meta?.date_bounds.max_date), 'day')
            }
          />
        </Form.Item>
        {meta?.date_bounds.min_date && meta?.date_bounds.max_date ? (
          <Typography.Paragraph type="secondary" style={{ marginTop: -12, fontSize: 12 }}>
            Available data: {meta.date_bounds.min_date} → {meta.date_bounds.max_date}.
            Leave empty for the full window.
          </Typography.Paragraph>
        ) : null}

        <Form.Item label="Tools" name="tool_ids">
          <Select
            mode="multiple"
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="All tools"
            maxTagCount="responsive"
            options={(meta?.tools ?? []).map((tool) => ({
              value: tool.tool_id,
              label: `${tool.tool_id} · ${tool.fab_site}`,
            }))}
          />
        </Form.Item>

        <Space size="middle" style={{ display: 'flex' }}>
          <Form.Item label="Family" name="tool_family" style={{ flex: 1 }}>
            <Select
              allowClear
              placeholder="All families"
              options={(meta?.families ?? []).map((family) => ({
                value: family,
                label: family,
              }))}
            />
          </Form.Item>
          <Form.Item label="Site" name="fab_site" style={{ flex: 1 }}>
            <Select
              allowClear
              placeholder="All sites"
              options={(meta?.sites ?? []).map((site) => ({ value: site, label: site }))}
            />
          </Form.Item>
        </Space>

        <Form.Item label="Shifts" name="shifts">
          <Checkbox.Group options={SHIFT_OPTIONS} style={{ display: 'flex', gap: 4 }} />
        </Form.Item>

        <Divider style={{ margin: '8px 0 20px' }} />

        <Form.Item label="Metric" name="metric">
          <Radio.Group options={METRIC_OPTIONS} />
        </Form.Item>

        <Space style={{ width: '100%', justifyContent: 'flex-end', marginTop: 12 }}>
          <Button onClick={handleReset}>Reset</Button>
          <Button type="primary" htmlType="submit">
            Apply filters
          </Button>
        </Space>
      </Form>
    </Drawer>
  )
}
