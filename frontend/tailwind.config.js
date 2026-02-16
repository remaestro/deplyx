/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono Variable', 'ui-monospace', 'monospace'],
      },
      colors: {
        brand: {
          50: '#eef2ff',
          100: '#e0e7ff',
          200: '#c7d2fe',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
          800: '#3730a3',
          900: '#312e81',
          950: '#1e1b4b',
        },
        mint: {
          400: '#34d399',
          500: '#06d6a0',
          600: '#059669',
        },
        surface: {
          dark: '#0f172a',
          'dark-secondary': '#1e293b',
          'dark-tertiary': '#334155',
          light: '#f8fafc',
          'light-secondary': '#f1f5f9',
          'light-tertiary': '#e2e8f0',
        },
        topo: {
          firewall: '#ef4444',
          switch: '#6366f1',
          router: '#8b5cf6',
          server: '#f59e0b',
          vlan: '#06b6d4',
          application: '#f59e0b',
          service: '#10b981',
          datacenter: '#3b82f6',
          cable: '#64748b',
          port: '#a855f7',
        },
      },
      borderRadius: {
        card: '12px',
        btn: '8px',
        input: '6px',
      },
      boxShadow: {
        card: '0 1px 3px 0 rgb(0 0 0 / 0.06), 0 1px 2px -1px rgb(0 0 0 / 0.06)',
        'card-hover': '0 4px 12px -1px rgb(0 0 0 / 0.1), 0 2px 6px -2px rgb(0 0 0 / 0.08)',
        'card-dark': '0 1px 3px 0 rgb(0 0 0 / 0.3), 0 1px 2px -1px rgb(0 0 0 / 0.3)',
        'card-dark-hover': '0 4px 12px -1px rgb(0 0 0 / 0.4), 0 2px 6px -2px rgb(0 0 0 / 0.3)',
        'glow-indigo': '0 0 12px 2px rgb(99 102 241 / 0.25)',
        'glow-red': '0 0 12px 2px rgb(239 68 68 / 0.25)',
        'glow-amber': '0 0 12px 2px rgb(245 158 11 / 0.25)',
        'glow-emerald': '0 0 12px 2px rgb(16 185 129 / 0.25)',
      },
      animation: {
        shimmer: 'shimmer 2s ease-in-out infinite',
        'pulse-ring': 'pulse-ring 1.5s ease-out infinite',
        'fade-in': 'fade-in 0.15s ease-out',
        'slide-up': 'slide-up 0.15s ease-out',
        'slide-in-right': 'slide-in-right 0.2s ease-out',
        'status-pulse': 'status-pulse 2s ease-in-out infinite',
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        'pulse-ring': {
          '0%': { transform: 'scale(1)', opacity: '0.6' },
          '100%': { transform: 'scale(1.8)', opacity: '0' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'slide-up': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in-right': {
          '0%': { opacity: '0', transform: 'translateX(16px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        'status-pulse': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.5' },
        },
      },
    },
  },
  plugins: [],
}
