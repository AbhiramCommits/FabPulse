import type { ReactNode } from 'react'
import { Breadcrumb } from 'antd'
import { HomeOutlined } from '@ant-design/icons'
import { Link, useLocation } from 'react-router-dom'

/** Route-aware breadcrumbs; the drill-down path mirrors the URL. */
export default function AppBreadcrumbs() {
  const location = useLocation()
  const parts = location.pathname.split('/').filter(Boolean)
  const items: Array<{ title: ReactNode }> = [
    {
      title: (
        <Link to={`/${location.search}`}>
          <HomeOutlined /> Fleet
        </Link>
      ),
    },
  ]

  if (parts[0] === 'tools') {
    if (parts.length === 1 || !parts[1]) {
      items.push({ title: 'Tools' })
    } else {
      items.push({ title: <Link to={`/tools${location.search}`}>Tools</Link> })
      items.push({ title: decodeURIComponent(parts[1]) })
    }
  } else if (parts[0] === 'report') {
    items.push({ title: 'Engineer report' })
  } else {
    items.push({ title: 'Overview' })
  }

  return <Breadcrumb items={items} style={{ marginBottom: 16 }} />
}
