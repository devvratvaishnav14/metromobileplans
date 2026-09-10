import { Birds } from './Birds'
import { Ferries } from './Ferries'

/**
 * Ambient life around the world — a few slow ferries on the water and a handful
 * of distant birds. Purely decorative; nothing here intercepts pointer events.
 * The animated water is mounted separately (it is structural, not an easter egg).
 */
export function Ambient() {
  return (
    <group>
      <Ferries />
      <Birds />
    </group>
  )
}
