import { describe, expect, it } from 'vitest'
import { SUPPORTED_MUNICIPALITY_IDS, isSupportedMunicipality } from './coverage'
import { getMunicipality, municipalities } from './municipalities'
import { DESTINATIONS } from '../scene/navigation/destinations'

/**
 * Guards the "Vancouver / Burnaby / Surrey must stay clickable" contract.
 *
 * The map only makes a municipality interactive when
 * `isSupportedMunicipality(id)` is true, and `useDestinationFlow`
 * dispatches the character only when `DESTINATIONS[id]` exists. If either the
 * supported list, the municipality data, or the nav destinations drift out of
 * alignment, a supported municipality silently stops working — this catches it.
 */
describe('V1 map coverage', () => {
  it('supports exactly Vancouver, Burnaby and Surrey', () => {
    expect([...SUPPORTED_MUNICIPALITY_IDS].sort()).toEqual(
      ['burnaby', 'surrey', 'vancouver'],
    )
  })

  it.each(SUPPORTED_MUNICIPALITY_IDS)('"%s" is a real municipality', (id) => {
    expect(municipalities.some((m) => m.id === id)).toBe(true)
    expect(getMunicipality(id)?.name).toBeTruthy()
  })

  it.each(SUPPORTED_MUNICIPALITY_IDS)(
    '"%s" has a nav destination the character can walk to',
    (id) => {
      const dest = DESTINATIONS[id]
      expect(dest).toBeDefined()
      expect(Number.isInteger(dest.node)).toBe(true)
      expect(Number.isFinite(dest.x)).toBe(true)
      expect(Number.isFinite(dest.z)).toBe(true)
    },
  )

  it('isSupportedMunicipality only accepts the supported ids', () => {
    for (const id of SUPPORTED_MUNICIPALITY_IDS) {
      expect(isSupportedMunicipality(id)).toBe(true)
    }
    for (const m of municipalities) {
      const expected = (SUPPORTED_MUNICIPALITY_IDS as readonly string[]).includes(
        m.id,
      )
      expect(isSupportedMunicipality(m.id)).toBe(expected)
    }
    expect(isSupportedMunicipality(null)).toBe(false)
    expect(isSupportedMunicipality(undefined)).toBe(false)
    expect(isSupportedMunicipality('richmond')).toBe(false)
  })
})
