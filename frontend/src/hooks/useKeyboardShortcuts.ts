import { useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppStore } from '../store/useAppStore'

/**
 * Global keyboard shortcuts (vim-style two-key combos).
 *
 * Navigation (g + key):
 *   g d  → Dashboard
 *   g c  → Changes
 *   g t  → Topology / Graph
 *   g n  → Connectors
 *   g p  → Policies
 *   g a  → Audit Log
 *
 * Actions:
 *   ?    → Show shortcuts help
 *   Esc  → Close command palette
 */

type ShortcutCallback = {
  onShowHelp: () => void
}

export function useKeyboardShortcuts({ onShowHelp }: ShortcutCallback) {
  const navigate = useNavigate()
  const pendingPrefix = useRef<string | null>(null)
  const prefixTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const resetPrefix = useCallback(() => {
    pendingPrefix.current = null
    if (prefixTimer.current) {
      clearTimeout(prefixTimer.current)
      prefixTimer.current = null
    }
  }, [])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Skip if user is typing in an input/textarea/select or contenteditable
      const target = e.target as HTMLElement
      if (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.tagName === 'SELECT' ||
        target.isContentEditable
      ) {
        return
      }

      // Skip if modifier keys held (except shift for ?)
      if (e.ctrlKey || e.altKey || e.metaKey) return

      const key = e.key.toLowerCase()

      // If we have a pending 'g' prefix
      if (pendingPrefix.current === 'g') {
        e.preventDefault()
        resetPrefix()
        switch (key) {
          case 'd': navigate('/'); return
          case 'c': navigate('/changes'); return
          case 't': navigate('/graph'); return
          case 'n': navigate('/connectors'); return
          case 'p': navigate('/policies'); return
          case 'a': navigate('/audit-log'); return
          default: return
        }
      }

      // Start 'g' prefix
      if (key === 'g') {
        pendingPrefix.current = 'g'
        prefixTimer.current = setTimeout(resetPrefix, 800)
        return
      }

      // Single-key shortcuts
      if (e.key === '?') {
        e.preventDefault()
        onShowHelp()
        return
      }

      if (key === 'escape') {
        const store = useAppStore.getState()
        if (store.commandPaletteOpen) {
          store.toggleCommandPalette()
        }
        return
      }
    }

    document.addEventListener('keydown', handler)
    return () => {
      document.removeEventListener('keydown', handler)
      resetPrefix()
    }
  }, [navigate, onShowHelp, resetPrefix])
}

/** All shortcuts for the help dialog */
export const SHORTCUTS = [
  { keys: ['⌘', 'K'], description: 'Command palette' },
  { keys: ['?'], description: 'Keyboard shortcuts help' },
  { keys: ['g', 'd'], description: 'Go to Dashboard' },
  { keys: ['g', 'c'], description: 'Go to Changes' },
  { keys: ['g', 't'], description: 'Go to Topology' },
  { keys: ['g', 'n'], description: 'Go to Connectors' },
  { keys: ['g', 'p'], description: 'Go to Policies' },
  { keys: ['g', 'a'], description: 'Go to Audit Log' },
  { keys: ['Esc'], description: 'Close palette / dialogs' },
]
