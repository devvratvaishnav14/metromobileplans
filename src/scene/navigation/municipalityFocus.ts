import * as THREE from 'three'
import { getMunicipality } from '../../data/municipalities'

/**
 * World-space centre of a municipality's top surface — the point the cinematic
 * "dive" pushes toward once the user confirms a selection.
 *
 * Municipality geometry is authored in a 2D map plane (x = East, y = North).
 * `<Municipalities>` lays it flat (rotate -90° about X) and drops it so the
 * extruded top surface sits at world y = 0, which maps (dx, dy) → (dx, 0, -dy).
 */
export function municipalityCenter(id: string): THREE.Vector3 | null {
  const m = getMunicipality(id)
  if (!m) return null

  let sx = 0
  let sy = 0
  let n = 0
  for (const poly of m.polygons) {
    for (const [x, y] of poly.outer) {
      sx += x
      sy += y
      n += 1
    }
  }
  if (n === 0) return null

  return new THREE.Vector3(sx / n, 0.5, -(sy / n))
}
