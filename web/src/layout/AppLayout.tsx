import { useMemo, useState } from 'react'
import {
  Button,
  Grid,
  Layout,
  Menu,
  Space,
  Tooltip,
  Typography,
  App as AntdApp,
  theme as antdTheme,
} from 'antd'
import {
  BarChartOutlined,
  CopyOutlined,
  DashboardOutlined,
  FileTextOutlined,
  FilterOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MoonOutlined,
  SunOutlined,
  TableOutlined,
  ThunderboltFilled,
} from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import type { FilterState } from '../api/types'
import AppBreadcrumbs from '../components/AppBreadcrumbs'
import { useMeta } from '../hooks/useData'
import { useFilterState } from '../hooks/useFilterState'
import FilterDrawer from './FilterDrawer'
import { useTheme } from './ThemeProvider'

const { Header, Sider, Content, Footer } = Layout
const { useBreakpoint } = Grid

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    try {
      const area = document.createElement('textarea')
      area.value = text
      area.style.position = 'fixed'
      area.style.opacity = '0'
      document.body.appendChild(area)
      area.select()
      const copied = document.execCommand('copy')
      document.body.removeChild(area)
      return copied
    } catch {
      return false
    }
  }
}

function activeFilterCount(filters: FilterState): number {
  return (
    (filters.from_date ? 1 : 0) +
    (filters.to_date ? 1 : 0) +
    (filters.tool_ids.length ? 1 : 0) +
    (filters.tool_family ? 1 : 0) +
    (filters.fab_site ? 1 : 0) +
    (filters.shifts.length ? 1 : 0) +
    (filters.metric !== 'throughput_wph' ? 1 : 0)
  )
}

/** Application shell: collapsible navigation, theme toggle, filter drawer, content. */
export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const { filters, setFilters, resetFilters } = useFilterState()
  const { mode, toggle } = useTheme()
  const meta = useMeta()
  const { token } = antdTheme.useToken()
  const { message } = AntdApp.useApp()
  const navigate = useNavigate()
  const location = useLocation()
  const screens = useBreakpoint()

  const selectedKey = useMemo(() => {
    if (location.pathname.startsWith('/tools')) return '/tools'
    if (location.pathname.startsWith('/report')) return '/report'
    return '/'
  }, [location.pathname])

  const handleCopyLink = async () => {
    const copied = await copyToClipboard(window.location.href)
    if (copied) {
      message.success('Shareable link copied to the clipboard')
    } else {
      message.warning('Copy failed — use your browser address bar')
    }
  }

  const filtersActive = activeFilterCount(filters)

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        collapsedWidth={0}
        breakpoint="lg"
        onCollapse={setCollapsed}
        trigger={null}
        width={224}
        style={{
          overflow: 'auto',
          height: '100vh',
          position: screens.lg ? 'sticky' : 'fixed',
          top: 0,
          left: 0,
          zIndex: 30,
          background: token.colorBgContainer,
          borderRight: `1px solid ${token.colorBorderSecondary}`,
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '20px 20px 16px',
            color: '#0f9e8c',
            fontWeight: 700,
            fontSize: 19,
            letterSpacing: 0.4,
            whiteSpace: 'nowrap',
          }}
        >
          <ThunderboltFilled style={{ fontSize: 24 }} />
          FabPulse
        </div>
        <Menu
          mode="inline"
          theme={mode === 'dark' ? 'dark' : 'light'}
          selectedKeys={[selectedKey]}
          onClick={({ key }) => {
            navigate(`${key}${location.search}`)
            if (!screens.lg) setCollapsed(true)
          }}
          items={[
            { key: '/', icon: <DashboardOutlined />, label: 'Fleet overview' },
            { key: '/tools', icon: <TableOutlined />, label: 'Tools' },
            { key: '/report', icon: <FileTextOutlined />, label: 'Engineer report' },
          ]}
          style={{ borderInlineEnd: 'none', background: 'transparent' }}
        />
        {!collapsed && screens.lg ? (
          <div style={{ padding: 20, opacity: 0.55, fontSize: 12, lineHeight: 1.6 }}>
            <BarChartOutlined /> Star-schema telemetry
            <br />
            {meta.data?.tools.length ?? '—'} tools · {meta.data?.date_bounds.min_date ?? '—'} →{' '}
            {meta.data?.date_bounds.max_date ?? '—'}
          </div>
        ) : null}
      </Sider>

      <Layout>
        <Header
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            paddingInline: screens.md ? 24 : 12,
            position: 'sticky',
            top: 0,
            zIndex: 20,
            background: token.colorBgContainer,
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            backdropFilter: 'blur(8px)',
          }}
        >
          <Button
            type="text"
            aria-label="Toggle navigation"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed((value) => !value)}
          />
          <Typography.Text strong style={{ fontSize: 16, whiteSpace: 'nowrap' }}>
            FabPulse
          </Typography.Text>
          {screens.md ? (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Semiconductor equipment analytics
            </Typography.Text>
          ) : null}
          <div style={{ flex: 1 }} />
          <Space size={4}>
            <Tooltip title="Copy a link to this exact view">
              <Button icon={<CopyOutlined />} onClick={handleCopyLink} aria-label="Copy link">
                {screens.sm ? 'Copy link' : null}
              </Button>
            </Tooltip>
            <Tooltip title="Filters">
              <Button
                icon={<FilterOutlined />}
                onClick={() => setDrawerOpen(true)}
                aria-label="Open filters"
              >
                {screens.sm ? 'Filters' : null}
                {filtersActive > 0 ? ` (${filtersActive})` : ''}
              </Button>
            </Tooltip>
            <Tooltip title={mode === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}>
              <Button
                type="text"
                aria-label="Toggle theme"
                icon={mode === 'dark' ? <SunOutlined /> : <MoonOutlined />}
                onClick={toggle}
              />
            </Tooltip>
          </Space>
        </Header>

        <Content
          style={{
            padding: screens.md ? '20px 24px 32px' : '12px 12px 24px',
            maxWidth: 1680,
            width: '100%',
            margin: '0 auto',
          }}
        >
          <AppBreadcrumbs />
          <Outlet />
        </Content>

        <Footer style={{ textAlign: 'center', fontSize: 12, opacity: 0.6 }}>
          FabPulse · synthetic fab telemetry · Postgres star schema · FastAPI · React 18
        </Footer>
      </Layout>

      <FilterDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        filters={filters}
        meta={meta.data}
        onApply={setFilters}
        onReset={resetFilters}
      />
    </Layout>
  )
}
