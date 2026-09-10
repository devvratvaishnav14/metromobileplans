import { Mountain } from './Mountain'
import { MOUNTAIN_RANGE } from './mountain-data'

/** Renders the stylised North Shore / northern mountain range. */
export function Mountains() {
  return (
    <group>
      {MOUNTAIN_RANGE.map((m, i) => (
        <Mountain key={i} {...m} />
      ))}
    </group>
  )
}
