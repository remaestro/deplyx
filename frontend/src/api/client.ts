import axios from 'axios'

const env = (import.meta as { env?: { VITE_API_URL?: string } }).env

export const apiClient = axios.create({
  baseURL: env?.VITE_API_URL ?? 'http://localhost:8000/api/v1',
  timeout: 120_000,
})

// Attach JWT token to every request
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('deplyx_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// On 401 redirect to login
apiClient.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('deplyx_token')
      localStorage.removeItem('deplyx_user')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  },
)
