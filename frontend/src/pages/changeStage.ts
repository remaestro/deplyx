import { apiClient } from '../api/client'

export type ChangeStageResponse = {
  change_id: string
  analysis_stage: string
  analysis_attempts: number
  analysis_last_error: string | null
  analysis_trace_id: string | null
}

const TERMINAL_STAGES = new Set(['finalised', 'failed'])

/**
 * Human-readable labels for each pipeline analysis stage.
 * Keys must match the backend `analysis_stage` column values.
 */
export const STAGE_LABELS: Record<string, string> = {
  fetching_data: 'Fetching Data',
  computing_impact: 'Computing Impact',
  scoring_risk: 'Scoring Risk',
  routing_workflow: 'Routing Workflow',
  finalised: 'Finalised',
  failed: 'Failed',
}

export const isAnalysisStageTerminal = (stage: string | null | undefined): boolean => {
  if (!stage) return false
  return TERMINAL_STAGES.has(stage)
}

export const formatAnalysisStageLabel = (stage: string | null | undefined): string => {
  if (!stage) return 'Pending'
  if (stage in STAGE_LABELS) return STAGE_LABELS[stage]
  return stage
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

export const fetchChangeStage = async (changeId: string): Promise<ChangeStageResponse> => {
  const response = await apiClient.get(`/changes/${changeId}/stage`)
  return response.data
}
