import { apiClient } from './client'

// ─── Types ─────────────────────────────────────────────────────────────────

export interface CatalogItem {
  type_id: string
  label: string
  category: string
  vendor: string
  model: string
  description: string
  icon_type: string
  image: string
  protocol: string
  default_port: number
  color: string
}

export interface LabContainer {
  id: string
  full_id: string
  name: string
  status: string   // 'running' | 'exited' | 'paused' | 'created' | 'restarting'
  type_id: string
  category: string
  image: string
  ip: string | null
  ports: Record<string, string | null>
  created: string
  labels: Record<string, string>
}

export interface SpawnRequest {
  type_id: string
  name: string
  custom_env?: Record<string, string>
}

export interface ContainerLogs {
  container_id: string
  logs: string
  lines: number
}

export interface ExecResult {
  // API devices
  status?: number
  data?: unknown
  error?: string
  // SSH devices
  output?: string
  stderr?: string | null
  exit_code?: number
  // Help
  type?: string
  protocol?: string
  commands?: string[]
  hint?: string
}

export interface ExecRequest {
  command: string
}

// ─── API calls ─────────────────────────────────────────────────────────────

/** Fetch the static device catalog (never changes at runtime). */
export const getCatalog = (): Promise<CatalogItem[]> =>
  apiClient.get('/lab/catalog').then((r) => r.data)

/** List all running/stopped lab containers. */
export const getContainers = (): Promise<LabContainer[]> =>
  apiClient.get('/lab/containers').then((r) => r.data)

/** Spawn a new container from the catalog. */
export const spawnContainer = (payload: SpawnRequest): Promise<LabContainer> =>
  apiClient.post('/lab/containers', payload).then((r) => r.data)

/** Remove a container (must be stopped first). */
export const removeContainer = (id: string): Promise<void> =>
  apiClient.delete(`/lab/containers/${id}`).then(() => undefined)

/** Start a stopped container. */
export const startContainer = (id: string): Promise<LabContainer> =>
  apiClient.post(`/lab/containers/${id}/start`).then((r) => r.data)

/** Stop a running container. */
export const stopContainer = (id: string): Promise<LabContainer> =>
  apiClient.post(`/lab/containers/${id}/stop`).then((r) => r.data)

/** Restart a container. */
export const restartContainer = (id: string): Promise<LabContainer> =>
  apiClient.post(`/lab/containers/${id}/restart`).then((r) => r.data)

/** Fetch recent log output. */
export const getContainerLogs = (id: string, lines = 150): Promise<ContainerLogs> =>
  apiClient.get(`/lab/containers/${id}/logs`, { params: { lines } }).then((r) => r.data)

/** Execute a command against a lab device. */
export const execCommand = (id: string, command: string): Promise<ExecResult> =>
  apiClient.post(`/lab/containers/${id}/exec`, { command }).then((r) => r.data)

/** Get available commands for a lab device. */
export const getExecHelp = (id: string): Promise<ExecResult> =>
  apiClient.get(`/lab/containers/${id}/exec/help`).then((r) => r.data)
