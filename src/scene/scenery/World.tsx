import { useMemo } from 'react'
import { BuildingField } from './BuildingField'
import { Mountains } from './Mountains'
import { Parks } from './Parks'
import { TreeField } from './TreeField'
import { Roads } from './roads/Roads'
import { generateScenery } from './scatter'

/**
 * The full miniature-world scenery layer for Metro Vancouver.
 *
 * Composition:
 *  - `Mountains`  — hand-placed stylised peaks along the northern edge
 *  - `Roads`      — decorative playmat road network + bridges (data in
 *                   `roads/network.ts`, which a future navigation layer will
 *                   also consume)
 *  - `Parks`      — lawn discs for named green areas
 *  - `BuildingField` / `TreeField` — instanced, procedurally scattered from
 *                   the real municipality shapes (deterministic seed)
 *
 * Everything here is decorative and ignores pointer events, so municipality
 * hover / labels / OrbitControls keep working underneath.
 */
const WORLD_SEED = 20260901

export function World() {
  const { buildings, trees } = useMemo(
    () => generateScenery(WORLD_SEED),
    [],
  )

  return (
    <group>
      <Mountains />
      <Roads />
      <Parks />
      <BuildingField items={buildings} />
      <TreeField items={trees} />
    </group>
  )
}
