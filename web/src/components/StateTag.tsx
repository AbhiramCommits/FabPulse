import { Tag } from 'antd'

const STATE_COLORS: Record<string, string> = {
  PRODUCTIVE: 'green',
  STANDBY: 'default',
  SCHEDULED_DOWN: 'blue',
  UNSCHEDULED_DOWN: 'red',
  ENGINEERING: 'purple',
}

/** Colour-coded equipment state tag used in tables and timelines. */
export default function StateTag({ state }: { state: string }) {
  return <Tag color={STATE_COLORS[state] ?? 'default'}>{state}</Tag>
}
