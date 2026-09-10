import { WORLD_MUNICIPALITIES, pointInMunicipality } from '../scenery/geo'
import { NAV_GRAPH } from './navGraph'

/**
 * One arrival anchor per municipality: the nav-graph node that best represents
 * "arriving" there. Preference order:
 *   1. a node that lies inside the municipality, nearest its centre
 *   2. otherwise the nearest node overall (he walks up to its edge)
 *
 * Because anchors are real graph nodes, routing to them always succeeds and
 * he never ends up in water or a building.
 */

export interface Destination {
  municipalityId: string
  name: string
  /** Nav-graph node index to route to. */
  node: number
  x: number
  z: number
  inside: boolean
}

function centroid(polys: { outer: [number, number][] }[]): [number, number] {
  let sx = 0
  let sz = 0
  let count = 0
  for (const p of polys) {
    for (const [x, z] of p.outer) {
      sx += x
      sz += z
      count++
    }
  }
  return [sx / count, sz / count]
}

function build(): Record<string, Destination> {
  const out: Record<string, Destination> = {}

  for (const m of WORLD_MUNICIPALITIES) {
    const [cx, cz] = centroid(m.polygons)

    let insideNode = -1
    let insideD = Infinity
    let anyNode = 0
    let anyD = Infinity

    for (let i = 0; i < NAV_GRAPH.nodes.length; i++) {
      const [nx, nz] = NAV_GRAPH.nodes[i]
      const dd = Math.hypot(nx - cx, nz - cz)
      if (dd < anyD) {
        anyD = dd
        anyNode = i
      }
      if (dd < insideD && pointInMunicipality(m, nx, nz)) {
        insideD = dd
        insideNode = i
      }
    }

    const inside = insideNode >= 0
    const node = inside ? insideNode : anyNode
    const [x, z] = NAV_GRAPH.nodes[node]
    out[m.id] = { municipalityId: m.id, name: m.name, node, x, z, inside }
  }

  return out
}

export const DESTINATIONS: Record<string, Destination> = build()
