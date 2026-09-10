import { ROAD_NETWORK } from '../scenery/roads/network'
import type { XZ } from '../scenery/geo'

/**
 * The hidden walkable graph.
 *
 * Built once, at import time, purely from `ROAD_NETWORK` *data* (never from the
 * decorative meshes). Each road centre-line contributes nodes at its vertices;
 * roads that cross or meet are stitched together at junction nodes; a final
 * connectivity pass guarantees the whole graph is one component so any
 * municipality is reachable from any start.
 *
 * The character controller routes over this — the visible roads are only a
 * reference for where it runs.
 */

export interface NavGraph {
  /** World XZ position of every node. */
  nodes: XZ[]
  /** adjacency[i] = neighbours of node i, with edge cost (distance). */
  adjacency: { to: number; cost: number }[][]
}

const WELD = 0.9 // nodes within this distance are the same node
const T_JOIN = 0.75 // a vertex this close to another road's segment joins it

/**
 * Hand-added links for spots where two roads clearly belong together in the
 * network but are just too far apart for the automatic weld / T-join (e.g. two
 * near-parallel roads through the same area). Each pair is snapped to its
 * nearest nodes and an edge is added. Keeps routes from taking silly detours.
 */
const CONNECTORS: [XZ, XZ][] = [
  // south-arterial's Vancouver end <-> vancouver-cross (Vancouver would
  // otherwise be a dead-end spur, forcing a detour north before heading east)
  [
    [-12.4, -1],
    [-10.9, -2.5],
  ],
  // south-arterial <-> delta-west near Delta
  [
    [-12.6, 1.8],
    [-12.8, 2.6],
  ],
]

const d = (a: XZ, b: XZ) => Math.hypot(a[0] - b[0], a[1] - b[1])

function segIntersect(p1: XZ, p2: XZ, p3: XZ, p4: XZ): XZ | null {
  const d1x = p2[0] - p1[0]
  const d1z = p2[1] - p1[1]
  const d2x = p4[0] - p3[0]
  const d2z = p4[1] - p3[1]
  const denom = d1x * d2z - d1z * d2x
  if (Math.abs(denom) < 1e-9) return null
  const t = ((p3[0] - p1[0]) * d2z - (p3[1] - p1[1]) * d2x) / denom
  const u = ((p3[0] - p1[0]) * d1z - (p3[1] - p1[1]) * d1x) / denom
  if (t < 0 || t > 1 || u < 0 || u > 1) return null
  return [p1[0] + t * d1x, p1[1] + t * d1z]
}

function closestOnSeg(p: XZ, a: XZ, b: XZ) {
  const abx = b[0] - a[0]
  const abz = b[1] - a[1]
  const len2 = abx * abx + abz * abz
  let t = len2 ? ((p[0] - a[0]) * abx + (p[1] - a[1]) * abz) / len2 : 0
  t = Math.max(0, Math.min(1, t))
  const point: XZ = [a[0] + t * abx, a[1] + t * abz]
  return { point, t, dist: d(p, point) }
}

function buildGraph(): NavGraph {
  const nodes: XZ[] = []
  const adjacency: { to: number; cost: number }[][] = []

  /** Get the index of an existing node within WELD, or add a new one. */
  const nodeOf = (p: XZ): number => {
    for (let i = 0; i < nodes.length; i++) {
      if (d(nodes[i], p) <= WELD) return i
    }
    nodes.push([p[0], p[1]])
    adjacency.push([])
    return nodes.length - 1
  }

  const addEdge = (a: number, b: number) => {
    if (a === b) return
    const cost = d(nodes[a], nodes[b])
    if (!adjacency[a].some((e) => e.to === b)) adjacency[a].push({ to: b, cost })
    if (!adjacency[b].some((e) => e.to === a)) adjacency[b].push({ to: a, cost })
  }

  const polylines: XZ[][] = ROAD_NETWORK.map((r) =>
    r.points.map((p) => [p[0], p[1]] as XZ),
  )

  // 1. every road's own vertices + consecutive edges
  const roadNodeIdx: number[][] = polylines.map((line) => line.map(nodeOf))
  for (const idx of roadNodeIdx) {
    for (let k = 0; k < idx.length - 1; k++) addEdge(idx[k], idx[k + 1])
  }

  // 2. true crossings between different roads -> a shared junction node
  for (let i = 0; i < polylines.length; i++) {
    for (let j = i + 1; j < polylines.length; j++) {
      const A = polylines[i]
      const B = polylines[j]
      for (let a = 0; a < A.length - 1; a++) {
        for (let b = 0; b < B.length - 1; b++) {
          const x = segIntersect(A[a], A[a + 1], B[b], B[b + 1])
          if (!x) continue
          const xi = nodeOf(x)
          addEdge(xi, roadNodeIdx[i][a])
          addEdge(xi, roadNodeIdx[i][a + 1])
          addEdge(xi, roadNodeIdx[j][b])
          addEdge(xi, roadNodeIdx[j][b + 1])
        }
      }
    }
  }

  // 3. T-junctions: a road's vertex sitting on another road's segment
  for (let i = 0; i < polylines.length; i++) {
    for (let v = 0; v < polylines[i].length; v++) {
      const p = polylines[i][v]
      for (let j = 0; j < polylines.length; j++) {
        if (j === i) continue
        const B = polylines[j]
        for (let b = 0; b < B.length - 1; b++) {
          const near = closestOnSeg(p, B[b], B[b + 1])
          if (near.dist <= T_JOIN && near.t > 0.04 && near.t < 0.96) {
            const pi = nodeOf(near.point)
            addEdge(pi, roadNodeIdx[i][v])
            addEdge(pi, roadNodeIdx[j][b])
            addEdge(pi, roadNodeIdx[j][b + 1])
          }
        }
      }
    }
  }

  // 3b. hand-added connectors
  for (const [p, q] of CONNECTORS) addEdge(nodeOf(p), nodeOf(q))

  // 4. connectivity — stitch any stranded component to the main one
  const components: number[][] = []
  const seen = new Uint8Array(nodes.length)
  for (let s = 0; s < nodes.length; s++) {
    if (seen[s]) continue
    const comp: number[] = []
    const stack = [s]
    seen[s] = 1
    while (stack.length) {
      const n = stack.pop()!
      comp.push(n)
      for (const e of adjacency[n]) {
        if (!seen[e.to]) {
          seen[e.to] = 1
          stack.push(e.to)
        }
      }
    }
    components.push(comp)
  }
  components.sort((a, b) => b.length - a.length)
  const main = components[0] ?? []
  for (let c = 1; c < components.length; c++) {
    let best = { a: -1, b: -1, dist: Infinity }
    for (const na of components[c]) {
      for (const nb of main) {
        const dd = d(nodes[na], nodes[nb])
        if (dd < best.dist) best = { a: na, b: nb, dist: dd }
      }
    }
    if (best.a >= 0) {
      addEdge(best.a, best.b)
      main.push(...components[c])
    }
  }

  return { nodes, adjacency }
}

export const NAV_GRAPH: NavGraph = buildGraph()

/** Index of the node nearest a world XZ point. */
export function nearestNode(x: number, z: number): number {
  let best = 0
  let bestD = Infinity
  for (let i = 0; i < NAV_GRAPH.nodes.length; i++) {
    const dd = Math.hypot(NAV_GRAPH.nodes[i][0] - x, NAV_GRAPH.nodes[i][1] - z)
    if (dd < bestD) {
      bestD = dd
      best = i
    }
  }
  return best
}

/**
 * Default start node — a central spot on the network (near the middle of the
 * east–west spine). Exported so the controller places him *exactly* on it.
 */
export const START_NODE = nearestNode(-1.2, -2.6)
