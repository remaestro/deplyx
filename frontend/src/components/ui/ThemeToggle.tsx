import { Sun, Moon } from 'lucide-react'
import { useAppStore } from '../../store/useAppStore'
import Tooltip from './Tooltip'

export default function ThemeToggle() {
  const { theme, setTheme } = useAppStore()

  return (
    <Tooltip content={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`} side="bottom">
      <button
        onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        className="rounded-btn p-2 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-surface-dark-tertiary transition-colors focus-ring"
        aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
      >
        {theme === 'dark' ? (
          <Sun className="h-4 w-4" />
        ) : (
          <Moon className="h-4 w-4" />
        )}
      </button>
    </Tooltip>
  )
}
