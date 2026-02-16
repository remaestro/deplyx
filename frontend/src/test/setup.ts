import '@testing-library/jest-dom'
import { beforeEach } from 'vitest'

import { useAppStore } from '../store/useAppStore'

beforeEach(() => {
  localStorage.clear()
  // Remove dark class for test environment consistency
  document.documentElement.classList.remove('dark')
  useAppStore.setState({
    token: null,
    user: null,
    isAuthenticated: false,
    selectedNodeId: null,
    selectedImpactChangeId: '',
    sidebarOpen: true,
    sidebarCollapsed: false,
    theme: 'dark',
    commandPaletteOpen: false,
  })
})
