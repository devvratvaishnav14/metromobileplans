import { useEffect, useMemo, useRef, type RefObject } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

/**
 * The GPS-style route line.
 *
 * The only visible part of the navigation system. Shows just the route the boy
 * is currently walking, as a smooth rounded orange tube sitting a hair above
 * the road:
 *   - draws forward when a destination is picked
 *   - trims away behind him as he advances (only the road ahead stays lit)
 *   - fades out once he arrives
 *
 * The graph / pathfinding stay completely invisible.
 */

const ROUTE_Y = 0.17 // just clears the raised road surface
const ROUTE_RADIUS = 0.1
const ROUTE_COLOR = '#ff8c1a'
const BASE_OPACITY = 0.9
const DRAW_IN = 0.3 // seconds to draw the route forward on appear
const FADE_OUT = 0.4 // seconds to fade the remainder after arrival
const TRIM_AHEAD = 0.25 // start the visible line a touch in front of his feet
const SAMPLE_SPACING = 0.28

interface Props {
  route: THREE.Vector3[] | null
  /** Live world position of the boy (written every frame by the controller). */
  characterPos: RefObject<THREE.Vector3>
  /** Distance he has travelled along the current route. */
  progress: RefObject<number>
}

export function RouteOverlay({ route, characterPos, progress }: Props) {
  const mesh = useRef<THREE.Mesh>(null)
  const material = useRef<THREE.MeshBasicMaterial>(null)

  // Smoothed centre-line — rebuilt only when the route changes.
  const spline = useMemo(() => {
    if (!route || route.length < 2) return null
    const raw = route.map((p) => new THREE.Vector3(p.x, ROUTE_Y, p.z))
    const curve = new THREE.CatmullRomCurve3(raw, false, 'catmullrom', 0)
    const length = curve.getLength()
    const n = Math.max(4, Math.min(280, Math.ceil(length / SAMPLE_SPACING)))
    const pts = curve.getSpacedPoints(n)
    const cum = [0]
    for (let i = 1; i < pts.length; i++) {
      cum.push(cum[i - 1] + pts[i].distanceTo(pts[i - 1]))
    }
    return { pts, cum, length }
  }, [route])

  const reveal = useRef(0)
  const opacity = useRef(0)
  const builtKey = useRef('')

  useEffect(() => {
    if (spline) {
      reveal.current = 0
      builtKey.current = ''
    }
  }, [spline])

  useFrame((_, dt) => {
    const m = mesh.current
    const mat = material.current
    if (!m || !mat) return
    const d = Math.min(dt, 0.05)

    if (!spline) {
      opacity.current = Math.max(0, opacity.current - d / FADE_OUT)
      mat.opacity = opacity.current * BASE_OPACITY
      m.visible = opacity.current > 0.02
      return
    }

    reveal.current = Math.min(1, reveal.current + d / DRAW_IN)
    opacity.current = Math.min(1, opacity.current + d / DRAW_IN)
    mat.opacity = opacity.current * BASE_OPACITY

    const front = spline.length * reveal.current
    const back = Math.min(
      (progress.current ?? 0) + TRIM_AHEAD,
      Math.max(0, front - 0.05),
    )

    // rebuild the tube only when the visible span has changed meaningfully
    const key = `${Math.round(back * 4)}_${Math.round(front * 4)}`
    if (key === builtKey.current) return
    builtKey.current = key

    const cp = characterPos.current
    const visible: THREE.Vector3[] = [new THREE.Vector3(cp.x, ROUTE_Y, cp.z)]
    for (let i = 0; i < spline.pts.length; i++) {
      const c = spline.cum[i]
      if (c > back + 1e-3 && c <= front + 1e-3) visible.push(spline.pts[i].clone())
    }
    if (reveal.current >= 1) {
      visible.push(spline.pts[spline.pts.length - 1].clone())
    }

    // drop near-coincident points (CatmullRom dislikes them)
    const clean: THREE.Vector3[] = [visible[0]]
    for (let i = 1; i < visible.length; i++) {
      if (visible[i].distanceToSquared(clean[clean.length - 1]) > 4e-4) {
        clean.push(visible[i])
      }
    }
    if (clean.length < 2) {
      m.visible = false
      return
    }

    m.visible = true
    const sub = new THREE.CatmullRomCurve3(clean, false, 'catmullrom', 0)
    const segments = Math.max(6, Math.min(320, clean.length * 4))
    m.geometry.dispose()
    m.geometry = new THREE.TubeGeometry(sub, segments, ROUTE_RADIUS, 7, false)
  })

  return (
    <mesh ref={mesh} renderOrder={3} raycast={() => null} visible={false}>
      <bufferGeometry />
      <meshBasicMaterial
        ref={material}
        color={ROUTE_COLOR}
        transparent
        opacity={0}
        depthWrite={false}
        toneMapped={false}
      />
    </mesh>
  )
}
