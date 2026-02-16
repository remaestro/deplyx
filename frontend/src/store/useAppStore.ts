import { create } from 'zustand'

type User = {
  id: number
  email: string
  role: string
}

type Theme = 'dark' | 'light'

type AppState = {
  // Auth
  token: string | null
  user: User | null
  isAuthenticated: boolean
  login: (token: string, user: User) => void
  logout: () => void

  // Graph
  selectedNodeId: string | null
  setSelectedNodeId: (id: string | null) => void
  selectedImpactChangeId: string
  setSelectedImpactChangeId: (id: string) => void

  // UI
  sidebarOpen: boolean
  setSidebarOpen: (open: boolean) => void
  sidebarCollapsed: boolean
  setSidebarCollapsed: (collapsed: boolean) => void

  // Theme
  theme: Theme
  setTheme: (theme: Theme) => void

  // Command palette
  commandPaletteOpen: boolean
  toggleCommandPalette: () => void
}

function applyThemeToDOM(theme: Theme) {
  if (typeof document !== 'undefined') {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }
}

export const useAppStore = create<AppState>((set, get) => {
  const storedToken = localStorage.getItem('deplyx_token')
  const storedUser = localStorage.getItem('deplyx_user')
  const storedImpactChangeId = localStorage.getItem('deplyx_graph_change_id')
  const storedTheme = (localStorage.getItem('deplyx_theme') as Theme) ?? 'dark'
  const storedCollapsed = localStorage.getItem('deplyx_sidebar_collapsed') === 'true'

  // Apply theme on store init
  applyThemeToDOM(storedTheme)

  return {
    token: storedToken,
    user: storedUser ? JSON.parse(storedUser) : null,
    isAuthenticated: !!storedToken,
    login: (token, user) => {
      localStorage.setItem('deplyx_token', token)
      localStorage.setItem('deplyx_user', JSON.stringify(user))
      set({ token, user, isAuthenticated: true })
    },
    logout: () => {
      localStorage.removeItem('deplyx_token')
      localStorage.removeItem('deplyx_user')
      localStorage.removeItem('deplyx_graph_change_id')
      set({ token: null, user: null, isAuthenticated: false })
    },

    selectedNodeId: null,
    setSelectedNodeId: (id) => set({ selectedNodeId: id }),
    selectedImpactChangeId: storedImpactChangeId ?? '',
    setSelectedImpactChangeId: (id) => {
      localStorage.setItem('deplyx_graph_change_id', id)
      set({ selectedImpactChangeId: id })
    },

    sidebarOpen: true,
    setSidebarOpen: (open) => set({ sidebarOpen: open }),

    sidebarCollapsed: storedCollapsed,
    setSidebarCollapsed: (collapsed) => {
      localStorage.setItem('deplyx_sidebar_collapsed', String(collapsed))
      set({ sidebarCollapsed: collapsed })
    },

    theme: storedTheme,
    setTheme: (theme) => {
      localStorage.setItem('deplyx_theme', theme)
      applyThemeToDOM(theme)
      set({ theme })
    },

    commandPaletteOpen: false,
    toggleCommandPalette: () => set({ commandPaletteOpen: !get().commandPaletteOpen }),
  }
})
