/**
 * Procedural, deterministic placement of buildings and trees across the whole
 * map. Pure data generation — no React, no Three.js. Runs once (memoised in
 * `World.tsx`).
 *
 * Approach: for each municipality, walk a jittered grid whose spacing comes
 * from that municipality's density. Keep a candidate only if it is on real
 * land, clear of roads, and outside any mountain footprint. A spatial hash
 * enforces minimum spacing so nothing overlaps.
 */
import { PALETTE } from './common'
import {
  WORLD_MUNICIPALITIES,
  distToBoundary,
  municipalityAt,
  nearestOnPolyline,
  pointInMunicipality,
  type WorldMunicipality,
} from './geo'
import { ROAD_NETWORK, ROAD_WIDTH } from './roads/network'
import { MOUNTAIN_RANGE } from './mountain-data'
import { PARKS } from './park-data'
import { makeRng, type Rng } from './prng'

export type BuildingKind = 'house' | 'mid' | 'tower'
export type RoofStyle = 'flat' | 'pyramid'

export interface BuildingInstance {
  position: [number, number, number]
  rotation: number
  width: number
  depth: number
  height: number
  colorHex: string
  roof: RoofStyle
  roofHex: string
}

export interface TreeInstance {
  position: [number, number, number]
  rotation: number
  scale: number
  variant: 'leafy' | 'conifer'
  colorHex: string
}

export interface Scenery {
  buildings: BuildingInstance[]
  trees: TreeInstance[]
}

/** Relative urban density per municipality (0 = rural, 1 = dense city). */
const DENSITY: Record<string, number> = {
  vancouver: 1.0,
  'new-westminster': 0.92,
  burnaby: 0.88,
  'north-vancouver-city': 0.82,
  richmond: 0.72,
  'white-rock': 0.7,
  'langley-city': 0.68,
  coquitlam: 0.6,
  'port-coquitlam': 0.58,
  'port-moody': 0.5,
  surrey: 0.5,
  'north-vancouver-district': 0.36,
  'maple-ridge': 0.32,
  delta: 0.3,
  'west-vancouver': 0.3,
  'langley-township': 0.28,
  'pitt-meadows': 0.26,
}

/** Downtown-Vancouver highrise cluster (world XZ) — extra tall buildings. */
const DOWNTOWN = { x: -13.7, z: -5.4, radius: 3.2 }

const ROOF_COLORS = [
  PALETTE.roof.terracotta,
  PALETTE.roof.slate,
  PALETTE.roof.cream,
  PALETTE.roof.teal,
]

const BUILDING_COLORS = Object.values(PALETTE.building)

interface RoadHit {
  dist: number
  angle: number
  half: number
}

function nearestRoad(x: number, z: number): RoadHit {
  let dist = Infinity
  let angle = 0
  let half = 0
  for (const road of ROAD_NETWORK) {
    const n = nearestOnPolyline(x, z, road.points)
    if (n.dist < dist) {
      dist = n.dist
      angle = n.angle
      half = ROAD_WIDTH[road.kind] / 2
    }
  }
  return { dist, angle, half }
}

/** True inside a mountain's building-exclusion footprint. */
function mountainOverlap(x: number, z: number, pad: number): boolean {
  return MOUNTAIN_RANGE.some((m) => {
    const d = Math.hypot(x - m.position[0], z - m.position[2])
    return d < m.radius * 0.85 + pad
  })
}

/** True only deep inside a mountain — trees may grow on the lower slopes. */
function deepInMountain(x: number, z: number): boolean {
  return MOUNTAIN_RANGE.some((m) => {
    const d = Math.hypot(x - m.position[0], z - m.position[2])
    return d < m.radius * 0.5
  })
}

function inAnyPark(x: number, z: number): boolean {
  return PARKS.some(
    (p) => Math.hypot(x - p.centre[0], z - p.centre[1]) < p.radius + 0.4,
  )
}

/** All four cardinal neighbours (distance d) are on some municipality's land. */
function surroundedByLand(x: number, z: number, d: number): boolean {
  return (
    !!municipalityAt(x + d, z) &&
    !!municipalityAt(x - d, z) &&
    !!municipalityAt(x, z + d) &&
    !!municipalityAt(x, z - d)
  )
}

/** Spatial hash for minimum-spacing checks. */
class SpatialHash {
  private cells = new Set<string>()
  private cell: number

  constructor(cell: number) {
    this.cell = cell
  }

  private key(cx: number, cz: number) {
    return `${cx},${cz}`
  }

  /** Occupied within one cell of (x, z)? */
  near(x: number, z: number): boolean {
    const cx = Math.round(x / this.cell)
    const cz = Math.round(z / this.cell)
    for (let dx = -1; dx <= 1; dx++) {
      for (let dz = -1; dz <= 1; dz++) {
        if (this.cells.has(this.key(cx + dx, cz + dz))) return true
      }
    }
    return false
  }

  has(x: number, z: number): boolean {
    return this.cells.has(
      this.key(Math.round(x / this.cell), Math.round(z / this.cell)),
    )
  }

  add(x: number, z: number) {
    this.cells.add(
      this.key(Math.round(x / this.cell), Math.round(z / this.cell)),
    )
  }
}

function pickBuildingKind(rng: Rng, density: number, downtown: boolean): BuildingKind {
  if (downtown) return rng.chance(0.78) ? 'tower' : 'mid'
  const towerChance = Math.max(0, density * 0.18 - 0.03)
  if (rng.chance(towerChance)) return 'tower'
  if (rng.chance(0.16 + density * 0.34)) return 'mid'
  return 'house'
}

function makeBuilding(
  rng: Rng,
  x: number,
  z: number,
  road: RoadHit,
  density: number,
): BuildingInstance {
  const downtown =
    Math.hypot(x - DOWNTOWN.x, z - DOWNTOWN.z) < DOWNTOWN.radius
  const kind = pickBuildingKind(rng, density, downtown)

  let width: number
  let depth: number
  let height: number
  let roof: RoofStyle
  if (kind === 'tower') {
    width = rng.range(1.0, 1.4)
    depth = rng.range(1.0, 1.4)
    height = downtown ? rng.range(3.4, 6.0) : rng.range(2.4, 4.2)
    roof = 'flat'
  } else if (kind === 'mid') {
    width = rng.range(0.85, 1.2)
    depth = rng.range(0.8, 1.1)
    height = rng.range(1.4, 2.3)
    roof = 'flat'
  } else {
    width = rng.range(0.55, 0.85)
    depth = rng.range(0.55, 0.8)
    height = rng.range(0.55, 0.95)
    roof = rng.chance(0.7) ? 'pyramid' : 'flat'
  }

  // Face the nearest road (or a random yaw if there is none close).
  let rotation: number
  if (road.dist < 9) {
    rotation = road.angle + (rng.chance(0.5) ? Math.PI / 2 : 0) + rng.range(-0.13, 0.13)
  } else {
    rotation = rng.range(0, Math.PI * 2)
  }

  return {
    position: [x, 0, z],
    rotation,
    width,
    depth,
    height,
    colorHex: rng.pick(BUILDING_COLORS),
    roof,
    roofHex: rng.pick(ROOF_COLORS),
  }
}

function makeTree(
  rng: Rng,
  x: number,
  z: number,
  forceLeafy = false,
): TreeInstance {
  const northern = z < -7
  const conifer = !forceLeafy && rng.chance(northern ? 0.6 : 0.22)
  return {
    position: [x, 0, z],
    rotation: rng.range(0, Math.PI * 2),
    scale: rng.range(0.5, 0.95),
    variant: conifer ? 'conifer' : 'leafy',
    colorHex: rng.pick(PALETTE.foliage),
  }
}

/**
 * Pass 1 — buildings. Rejection-samples toward a target count derived from the
 * municipality's land area and density, so counts stay sensible whatever the
 * polygon shape.
 */
function scatterBuildings(
  m: WorldMunicipality,
  rng: Rng,
  buildings: BuildingInstance[],
  hash: SpatialHash,
) {
  const density = DENSITY[m.id] ?? 0.32
  const [minX, minZ, maxX, maxZ] = m.bbox
  const raw = Math.round(m.area * (0.06 + density * 0.26))
  // Floor so small dense towns still read; cap so big areas don't dominate.
  const target = Math.min(26, Math.max(density > 0.6 ? 6 : 0, raw))
  const maxTries = Math.max(target * 120, 500)
  // Settlements hug the road network, leaving open green between them.
  const nearRoadMax = 1.5 + density * 2.4

  let placed = 0
  for (let tries = 0; placed < target && tries < maxTries; tries++) {
    const x = rng.range(minX, maxX)
    const z = rng.range(minZ, maxZ)

    if (!pointInMunicipality(m, x, z)) continue
    // Keep buildings back from any coastline, but allow them right up to an
    // inland border with a neighbouring municipality.
    if (distToBoundary(m, x, z) < 0.4 || !surroundedByLand(x, z, 0.9)) continue
    if (hash.has(x, z)) continue
    if (inAnyPark(x, z)) continue
    if (mountainOverlap(x, z, 0.5)) continue

    const road = nearestRoad(x, z)
    if (road.dist < road.half + 0.12) continue
    if (road.dist > nearRoadMax) continue

    buildings.push(makeBuilding(rng, x, z, road, density))
    hash.add(x, z)
    placed++
  }
}

/**
 * Pass 2 — trees. Also a targeted rejection sample: greener where it is less
 * built-up, filling the gaps between buildings and along the edges.
 */
function scatterTrees(
  m: WorldMunicipality,
  rng: Rng,
  trees: TreeInstance[],
  buildingHash: SpatialHash,
  treeHash: SpatialHash,
) {
  const density = DENSITY[m.id] ?? 0.32
  const [minX, minZ, maxX, maxZ] = m.bbox
  const target = Math.min(28, Math.round(m.area * (0.16 - density * 0.06)))
  const maxTries = Math.max(target * 45, 200)

  let placed = 0
  for (let tries = 0; placed < target && tries < maxTries; tries++) {
    const x = rng.range(minX, maxX)
    const z = rng.range(minZ, maxZ)

    if (!pointInMunicipality(m, x, z)) continue
    if (distToBoundary(m, x, z) < 0.3 && !surroundedByLand(x, z, 0.6)) continue
    if (treeHash.near(x, z)) continue
    if (buildingHash.has(x, z)) continue
    if (inAnyPark(x, z)) continue
    if (deepInMountain(x, z)) continue

    const road = nearestRoad(x, z)
    if (road.dist < road.half + 0.05) continue

    trees.push(makeTree(rng, x, z))
    treeHash.add(x, z)
    placed++
  }
}

function scatterParks(rng: Rng, trees: TreeInstance[], treeHash: SpatialHash) {
  for (const park of PARKS) {
    for (let i = 0; i < park.trees; i++) {
      const a = rng.range(0, Math.PI * 2)
      const r = Math.sqrt(rng.next()) * park.radius
      const x = park.centre[0] + Math.cos(a) * r
      const z = park.centre[1] + Math.sin(a) * r
      if (!municipalityAt(x, z)) continue
      const road = nearestRoad(x, z)
      if (road.dist < road.half + 0.1) continue
      trees.push(makeTree(rng, x, z, rng.chance(0.75)))
      treeHash.add(x, z)
    }
  }
}

export function generateScenery(seed: number): Scenery {
  const rng = makeRng(seed)
  const buildings: BuildingInstance[] = []
  const trees: TreeInstance[] = []
  const buildingHash = new SpatialHash(1.2)
  const treeHash = new SpatialHash(1.1)

  for (const m of WORLD_MUNICIPALITIES) {
    scatterBuildings(m, rng, buildings, buildingHash)
  }
  for (const m of WORLD_MUNICIPALITIES) {
    scatterTrees(m, rng, trees, buildingHash, treeHash)
  }
  scatterParks(rng, trees, treeHash)

  return { buildings, trees }
}
