import { describe, expect, it } from 'vitest'

import { resolveTopologyNodeLabel } from '../pages/GraphPage'

describe('display name UI helpers', () => {
  it('prefers display_name over label and id', () => {
    expect(resolveTopologyNodeLabel({ id: 'FW-1', label: 'Firewall', display_name: 'Fortinet Firewall — fw-dc1-01' }))
      .toBe('Fortinet Firewall — fw-dc1-01')
  })

  it('falls back to label then id', () => {
    expect(resolveTopologyNodeLabel({ id: 'FW-1', label: 'Firewall' })).toBe('Firewall')
    expect(resolveTopologyNodeLabel({ id: 'FW-1' })).toBe('FW-1')
  })
})
