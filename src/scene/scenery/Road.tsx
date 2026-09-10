import { useEffect, useMemo } from 'react'
import * as THREE from 'three'
import { PALETTE, ignoreRaycast } from './common'

export interface RoadProps {
  /** Centre-line points in world XZ (metres). Two or more. */
  points: [number, number][]
  /** Carriageway width. */
  width?: number
  /** Surface colour. */
  color?: string
  /** Draw a subtle dashed centre line (use for the larger roads). */
  markings?: boolean
  /** Height of the surface above the ground (playmat layering). */
  lift?: number
}

/**
 * Flat horizontal ribbon following a poly-line centre-line, with rounded caps
 * at the two ends. Built directly in the XZ plane, then normals are recomputed,
 * so it lights evenly like a smooth surface.
 */
function ribbonGeometry(
  points: THREE.Vector2[],
  width: number,
  round: boolean,
): THREE.BufferGeometry {
  const half = width / 2
  const left: THREE.Vector2[] = []
  const right: THREE.Vector2[] = []
  const dirs: THREE.Vector2[] = []
  for (let i = 0; i < points.length; i++) {
    const prev = points[i - 1] ?? points[i]
    const next = points[i + 1] ?? points[i]
    const dir = next.clone().sub(prev)
    if (dir.lengthSq() === 0) dir.set(1, 0)
    dir.normalize()
    dirs.push(dir)
    const normal = new THREE.Vector2(-dir.y, dir.x)
    left.push(points[i].clone().addScaledVector(normal, half))
    right.push(points[i].clone().addScaledVector(normal, -half))
  }

  const position: number[] = []
  const tri = (a: THREE.Vector2, b: THREE.Vector2, c: THREE.Vector2) => {
    position.push(a.x, 0, a.y, b.x, 0, b.y, c.x, 0, c.y)
  }

  for (let i = 0; i < points.length - 1; i++) {
    tri(left[i], left[i + 1], right[i])
    tri(right[i], left[i + 1], right[i + 1])
  }

  if (round) {
    const cap = (centre: THREE.Vector2, forward: THREE.Vector2, sign: number) => {
      const start =
        Math.atan2(forward.y, forward.x) + (sign > 0 ? -Math.PI / 2 : Math.PI / 2)
      const steps = 8
      for (let s = 0; s < steps; s++) {
        const a0 = start + (Math.PI * s) / steps
        const a1 = start + (Math.PI * (s + 1)) / steps
        tri(
          centre,
          new THREE.Vector2(centre.x + Math.cos(a0) * half, centre.y + Math.sin(a0) * half),
          new THREE.Vector2(centre.x + Math.cos(a1) * half, centre.y + Math.sin(a1) * half),
        )
      }
    }
    cap(points[0], dirs[0], -1)
    cap(points[points.length - 1], dirs[points.length - 1], 1)
  }

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(position, 3))
  geometry.computeVertexNormals()
  return geometry
}

/** All centre-line dashes merged into one geometry (one draw call per road). */
function dashGeometry(
  points: THREE.Vector2[],
  spacing = 2.0,
  dashLen = 0.55,
  dashWidth = 0.09,
): THREE.BufferGeometry {
  const position: number[] = []
  const quad = (cx: number, cz: number, angle: number) => {
    const dx = Math.cos(angle)
    const dz = Math.sin(angle)
    const hx = (dx * dashLen) / 2
    const hz = (dz * dashLen) / 2
    const wx = (-dz * dashWidth) / 2
    const wz = (dx * dashWidth) / 2
    const p = [
      [cx - hx + wx, cz - hz + wz],
      [cx + hx + wx, cz + hz + wz],
      [cx + hx - wx, cz + hz - wz],
      [cx - hx - wx, cz - hz - wz],
    ]
    position.push(p[0][0], 0, p[0][1], p[1][0], 0, p[1][1], p[2][0], 0, p[2][1])
    position.push(p[0][0], 0, p[0][1], p[2][0], 0, p[2][1], p[3][0], 0, p[3][1])
  }

  let travelled = 0
  let next = spacing / 2
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i]
    const b = points[i + 1]
    const seg = b.clone().sub(a)
    const len = seg.length()
    const angle = Math.atan2(seg.y, seg.x)
    while (next <= travelled + len) {
      const t = (next - travelled) / len
      quad(a.x + seg.x * t, a.y + seg.y * t, angle)
      next += spacing
    }
    travelled += len
  }

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(position, 3))
  geometry.computeVertexNormals()
  return geometry
}

/**
 * A stylised toy / playmat road: a smooth warm-grey surface layered just above
 * the green ground, with rounded ends, a slightly wider darker lip for a soft
 * edge, and optional dashed centre markings.
 *
 * Decorative only — ignores pointer events. Rendering only; the routing data
 * lives in `roads/network.ts`.
 */
export function Road({
  points,
  width = 1.4,
  color = PALETTE.road,
  markings = false,
  lift = 0.06,
}: RoadProps) {
  const pts = useMemo(
    () => points.map(([x, z]) => new THREE.Vector2(x, z)),
    [points],
  )
  const surface = useMemo(() => ribbonGeometry(pts, width, true), [pts, width])
  const lip = useMemo(() => ribbonGeometry(pts, width + 0.12, true), [pts, width])
  const dashes = useMemo(
    () => (markings ? dashGeometry(pts) : null),
    [pts, markings],
  )

  useEffect(() => {
    return () => {
      surface.dispose()
      lip.dispose()
      dashes?.dispose()
    }
  }, [surface, lip, dashes])

  return (
    <group>
      <mesh
        geometry={lip}
        position={[0, lift - 0.02, 0]}
        raycast={ignoreRaycast}
        receiveShadow
      >
        <meshStandardMaterial
          color={PALETTE.roadEdge}
          roughness={0.95}
          side={THREE.DoubleSide}
        />
      </mesh>

      <mesh
        geometry={surface}
        position={[0, lift, 0]}
        raycast={ignoreRaycast}
        receiveShadow
      >
        <meshStandardMaterial color={color} roughness={0.7} side={THREE.DoubleSide} />
      </mesh>

      {dashes && (
        <mesh geometry={dashes} position={[0, lift + 0.013, 0]} raycast={ignoreRaycast}>
          <meshStandardMaterial
            color={PALETTE.roadMarking}
            roughness={0.6}
            side={THREE.DoubleSide}
          />
        </mesh>
      )}
    </group>
  )
}
