/**
 * Geometry helpers for placing scenery against the real municipality shapes.
 *
 * The municipality data is authored in a 2D map plane ([x, y], +y = North).
 * The rendered world uses [x, 0, z] with the land top at y = 0 and North along
 * -z, so map (x, y) -> world (x, -y). Everything here works in that world XZ
 * space so scatter, roads and the (future) navigation layer all share one
 * coordinate system.
 */
import { municipalities } from '../../data/municipalities'

export type XZ = [number, number]

export interface WorldPolygon {
  outer: XZ[]
  holes: XZ[][]
}

export interface WorldMunicipality {
  id: string
  name: string
  polygons: WorldPolygon[]
  /** [minX, minZ, maxX, maxZ] */
  bbox: [number, number, number, number]
  /** Land area in world units², holes subtracted. */
  area: number
}

function ringArea(ring: XZ[]): number {
  let sum = 0
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    sum += (ring[j][0] + ring[i][0]) * (ring[j][1] - ring[i][1])
  }
  return Math.abs(sum) / 2
}

const toWorld = ([x, y]: readonly [number, number]): XZ => [x, -y]

export const WORLD_MUNICIPALITIES: WorldMunicipality[] = municipalities.map((m) => {
  const polygons: WorldPolygon[] = m.polygons.map((p) => ({
    outer: p.outer.map(toWorld),
    holes: p.holes.map((h) => h.map(toWorld)),
  }))
  let minX = Infinity
  let minZ = Infinity
  let maxX = -Infinity
  let maxZ = -Infinity
  for (const poly of polygons) {
    for (const [x, z] of poly.outer) {
      if (x < minX) minX = x
      if (x > maxX) maxX = x
      if (z < minZ) minZ = z
      if (z > maxZ) maxZ = z
    }
  }
  let area = 0
  for (const poly of polygons) {
    area += ringArea(poly.outer)
    for (const hole of poly.holes) area -= ringArea(hole)
  }

  return {
    id: m.id,
    name: m.name,
    polygons,
    bbox: [minX, minZ, maxX, maxZ],
    area,
  }
})

function pointInRing(x: number, z: number, ring: XZ[]): boolean {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, zi] = ring[i]
    const [xj, zj] = ring[j]
    if (zi > z !== zj > z && x < ((xj - xi) * (z - zi)) / (zj - zi) + xi) {
      inside = !inside
    }
  }
  return inside
}

export function pointInMunicipality(
  m: WorldMunicipality,
  x: number,
  z: number,
): boolean {
  return m.polygons.some(
    (p) =>
      pointInRing(x, z, p.outer) && !p.holes.some((h) => pointInRing(x, z, h)),
  )
}

/** Which municipality (if any) covers this world point. */
export function municipalityAt(x: number, z: number): WorldMunicipality | undefined {
  return WORLD_MUNICIPALITIES.find((m) => pointInMunicipality(m, x, z))
}

export function distToSegment(
  px: number,
  pz: number,
  ax: number,
  az: number,
  bx: number,
  bz: number,
): number {
  const dx = bx - ax
  const dz = bz - az
  const lenSq = dx * dx + dz * dz
  const t = lenSq === 0 ? 0 : Math.max(0, Math.min(1, ((px - ax) * dx + (pz - az) * dz) / lenSq))
  const cx = ax + t * dx
  const cz = az + t * dz
  return Math.hypot(px - cx, pz - cz)
}

export interface NearestPath {
  dist: number
  /** Heading of the closest segment, radians (atan2(dz, dx)). */
  angle: number
}

/** Shortest distance from a world point to a municipality's boundary. */
export function distToBoundary(
  m: WorldMunicipality,
  x: number,
  z: number,
): number {
  let best = Infinity
  for (const poly of m.polygons) {
    for (const ring of [poly.outer, ...poly.holes]) {
      for (let i = 0; i < ring.length; i++) {
        const [ax, az] = ring[i]
        const [bx, bz] = ring[(i + 1) % ring.length]
        const d = distToSegment(x, z, ax, az, bx, bz)
        if (d < best) best = d
      }
    }
  }
  return best
}

/** Closest approach of a point to a poly-line, plus that segment's heading. */
export function nearestOnPolyline(
  px: number,
  pz: number,
  points: readonly XZ[],
): NearestPath {
  let best = Infinity
  let angle = 0
  for (let i = 0; i < points.length - 1; i++) {
    const [ax, az] = points[i]
    const [bx, bz] = points[i + 1]
    const d = distToSegment(px, pz, ax, az, bx, bz)
    if (d < best) {
      best = d
      angle = Math.atan2(bz - az, bx - ax)
    }
  }
  return { dist: best, angle }
}
