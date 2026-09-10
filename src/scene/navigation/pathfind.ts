import * as THREE from 'three'
import { NAV_GRAPH, nearestNode } from './navGraph'

/**
 * Dijkstra shortest path over the nav graph (small graph — no heap needed).
 * Returns the list of node indices from `start` to `goal`, or [] if
 * unreachable (which should not happen — the graph is one component).
 */
export function shortestNodePath(start: number, goal: number): number[] {
  const n = NAV_GRAPH.nodes.length
  const distTo = new Array<number>(n).fill(Infinity)
  const prev = new Array<number>(n).fill(-1)
  const done = new Uint8Array(n)
  distTo[start] = 0

  for (let iter = 0; iter < n; iter++) {
    let u = -1
    let best = Infinity
    for (let i = 0; i < n; i++) {
      if (!done[i] && distTo[i] < best) {
        best = distTo[i]
        u = i
      }
    }
    if (u === -1 || u === goal) break
    done[u] = 1
    for (const e of NAV_GRAPH.adjacency[u]) {
      const nd = distTo[u] + e.cost
      if (nd < distTo[e.to]) {
        distTo[e.to] = nd
        prev[e.to] = u
      }
    }
  }

  if (distTo[goal] === Infinity) return []
  const path: number[] = []
  for (let at = goal; at !== -1; at = prev[at]) path.push(at)
  path.reverse()
  return path
}

/**
 * Full route as world-space waypoints: from the character's current position,
 * onto the network at the nearest node, along the graph to `goalNode`.
 * The current position is prepended so he walks smoothly onto the road
 * rather than snapping.
 */
export function routeFrom(
  fromX: number,
  fromZ: number,
  goalNode: number,
): THREE.Vector3[] {
  const startNode = nearestNode(fromX, fromZ)
  const nodePath = shortestNodePath(startNode, goalNode)
  if (nodePath.length === 0) return []

  const pts: THREE.Vector3[] = [new THREE.Vector3(fromX, 0, fromZ)]
  for (const ni of nodePath) {
    const [x, z] = NAV_GRAPH.nodes[ni]
    pts.push(new THREE.Vector3(x, 0, z))
  }

  // Drop a leading waypoint if he is basically already there (avoids a
  // tiny backwards hop onto the nearest node).
  if (pts.length > 2 && pts[0].distanceTo(pts[1]) < 0.4) pts.splice(1, 1)

  return pts
}
