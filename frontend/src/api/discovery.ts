import { apiClient } from './client'

export type DiscoveryResult = {
  id: number
  session_id: number
  host: string
  name_hint: string | null
  source_kind: string
  status: string
  selected_connector_type: string | null
  suggested_connector_types: string[]
  preflight_status: string
  bootstrap_status: string
  connector_id: number | null
  connector_name: string | null
  probe_detail: Record<string, unknown>
  facts: Record<string, unknown>
  classification_reasons: string[]
  bootstrap_detail: Record<string, unknown> | null
  error: string | null
  created_at: string
  updated_at: string
}

export type DiscoveryEvidence = {
  reachable?: boolean
  service_detected?: boolean
  ssh_manageable?: boolean
  api_manageable?: boolean
  snmp_identified?: boolean
}

export type DiscoverySession = {
  id: number
  name: string | null
  status: string
  input_payload: Record<string, unknown>
  ports: number[]
  timeout_seconds: number
  target_count: number
  summary: Record<string, unknown> | null
  started_at: string | null
  completed_at: string | null
  last_error: string | null
  created_at: string
  updated_at: string
}

export type DiscoverySessionDetail = DiscoverySession & {
  results: DiscoveryResult[]
}

export type DiscoverySessionCreatePayload = {
  name?: string
  targets?: string[]
  cidrs?: string[]
  inventory?: Array<{
    host: string
    name?: string
    connector_type?: string
    metadata?: Record<string, unknown>
  }>
  ports?: number[]
  timeout_seconds?: number
}

export type DiscoveryBootstrapPayload = {
  connector_defaults?: Record<string, Record<string, unknown>>
  default_config?: Record<string, unknown>
  sync_mode?: string
  sync_interval_minutes?: number
  run_sync?: boolean
  allow_ambiguous?: boolean
  on_existing?: string
  items?: Array<{
    result_id: number
    connector_type?: string
    run_sync?: boolean
  }>
}

export type DiscoveryBootstrapResponse = {
  session_id: number
  processed: number
  created: number
  synced: number
  skipped: number
  errors: number
  items: Array<{
    result_id: number
    host: string
    connector_type: string | null
    connector_id: number | null
    connector_name: string | null
    preflight_status: string
    bootstrap_status: string
    detail: Record<string, unknown>
  }>
}

export const discoveryApi = {
  async listSessions(): Promise<DiscoverySession[]> {
    const response = await apiClient.get<DiscoverySession[]>('/discovery/sessions')
    return response.data
  },

  async getSession(sessionId: number): Promise<DiscoverySessionDetail> {
    const response = await apiClient.get<DiscoverySessionDetail>(`/discovery/sessions/${sessionId}`)
    return response.data
  },

  async createSession(payload: DiscoverySessionCreatePayload): Promise<DiscoverySessionDetail> {
    const response = await apiClient.post<DiscoverySessionDetail>('/discovery/sessions', payload)
    return response.data
  },

  async bootstrapSession(
    sessionId: number,
    payload: DiscoveryBootstrapPayload,
  ): Promise<DiscoveryBootstrapResponse> {
    const response = await apiClient.post<DiscoveryBootstrapResponse>(
      `/discovery/sessions/${sessionId}/bootstrap`,
      payload,
    )
    return response.data
  },
}
