import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Button, Result } from 'antd'
import AppLayout from './layout/AppLayout'
import { ThemeProvider } from './layout/ThemeProvider'
import FleetOverview from './pages/FleetOverview'
import ToolsPage from './pages/ToolsPage'
import ToolDetailPage from './pages/ToolDetailPage'
import ReportPage from './pages/ReportPage'

function NotFound() {
  return (
    <Result
      status="404"
      title="Page not found"
      subTitle="The FabPulse console does not have a route here."
      extra={
        <Button type="primary" href="/">
          Back to the fleet overview
        </Button>
      }
    />
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<FleetOverview />} />
            <Route path="tools" element={<ToolsPage />} />
            <Route path="tools/:toolId" element={<ToolDetailPage />} />
            <Route path="report" element={<ReportPage />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  )
}
