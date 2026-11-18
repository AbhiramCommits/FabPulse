import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { App as AntdApp, ConfigProvider, theme as antdTheme } from 'antd'

export type ThemeMode = 'light' | 'dark'

interface ThemeContextValue {
  mode: ThemeMode
  toggle: () => void
  setMode: (mode: ThemeMode) => void
}

const STORAGE_KEY = 'fabpulse-theme'
const ThemeContext = createContext<ThemeContextValue | null>(null)

function initialMode(): ThemeMode {
  if (typeof window === 'undefined') return 'light'
  try {
    return window.localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

/**
 * Ant Design token provider with a persisted light/dark toggle. Charts read the
 * same mode from context so palettes switch together with the UI.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(initialMode)

  useEffect(() => {
    document.documentElement.dataset.theme = mode
    try {
      window.localStorage.setItem(STORAGE_KEY, mode)
    } catch {
      // Private-mode browsers can reject localStorage; the UI still works.
    }
  }, [mode])

  const setMode = useCallback((next: ThemeMode) => setModeState(next), [])
  const toggle = useCallback(
    () => setModeState((current) => (current === 'dark' ? 'light' : 'dark')),
    [],
  )
  const value = useMemo(() => ({ mode, toggle, setMode }), [mode, toggle, setMode])

  return (
    <ConfigProvider
      theme={{
        algorithm: mode === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: {
          colorPrimary: '#0f9e8c',
          colorInfo: '#0f9e8c',
          borderRadius: 8,
          fontFamily: "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        },
      }}
    >
      <ThemeContext.Provider value={value}>
        <AntdApp>{children}</AntdApp>
      </ThemeContext.Provider>
    </ConfigProvider>
  )
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext)
  if (!context) throw new Error('useTheme must be used inside ThemeProvider')
  return context
}
