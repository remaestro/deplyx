import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import ChangesPage from './pages/ChangesPage'
import ChangeDetailPage from './pages/ChangeDetailPage'
import GraphPage from './pages/GraphPage'
import ConnectorsPage from './pages/ConnectorsPage'
import PoliciesPage from './pages/PoliciesPage'
import AuditLogPage from './pages/AuditLogPage'
import { useAppStore } from './store/useAppStore'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAppStore((s) => s.isAuthenticated)
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/changes" element={<ChangesPage />} />
        <Route path="/changes/:id" element={<ChangeDetailPage />} />
        <Route path="/graph" element={<GraphPage />} />
        <Route path="/connectors" element={<ConnectorsPage />} />
        <Route path="/policies" element={<PoliciesPage />} />
        <Route path="/audit-log" element={<AuditLogPage />} />
      </Route>
    </Routes>
  )
}

export default App
