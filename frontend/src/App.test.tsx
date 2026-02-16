import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import App from './App'
import { ToastProvider } from './components/ui'

describe('App routing', () => {
  it('redirects unauthenticated users to login', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })

    render(
      <MemoryRouter initialEntries={['/']}>
        <QueryClientProvider client={queryClient}>
          <ToastProvider>
            <App />
          </ToastProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Change Intelligence Engine')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign In' })).toBeInTheDocument()
  })
})
