import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { ToastProvider } from './components/ui/Toast'
import { TooltipProvider } from './components/ui/Tooltip'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <ToastProvider>
            <App />
          </ToastProvider>
        </TooltipProvider>
      </QueryClientProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
