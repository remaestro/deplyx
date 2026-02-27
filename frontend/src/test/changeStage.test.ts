import { describe, expect, it } from 'vitest'

import { formatAnalysisStageLabel, isAnalysisStageTerminal } from '../pages/changeStage'

describe('changeStage helpers', () => {
  it('formats stage labels', () => {
    expect(formatAnalysisStageLabel('computing_impact')).toBe('Computing Impact')
  })

  it('detects terminal stages', () => {
    expect(isAnalysisStageTerminal('finalised')).toBe(true)
    expect(isAnalysisStageTerminal('failed')).toBe(true)
    expect(isAnalysisStageTerminal('scoring_risk')).toBe(false)
  })
})
