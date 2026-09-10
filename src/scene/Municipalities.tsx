import { useEffect, useMemo, useRef, useState } from 'react'
import { Html, Line } from '@react-three/drei'
import { useFrame, type ThreeEvent } from '@react-three/fiber'
import * as THREE from 'three'
import {
  COLORS,
  HOVER_EMISSIVE,
  HOVER_LERP_RATE,
  TERRAIN_HEIGHT,
} from './config'
import {
  municipalities,
  type Municipality,
  type Point,
  type Polygon,
} from '../data/municipalities'
import { isSupportedMunicipality } from '../data/coverage'

/** Small lift so the boundary lines sit cleanly on top of the land cap. */
const OUTLINE_LIFT = 0.02
/** How far above the top surface the labels float (scene units). */
const LABEL_LIFT = 2.4
/** Faint always-on glow for the supported (choosable) municipalities. */
const REST_GLOW = 0.22
/** Stable no-op raycast for inert (non-coverage) municipality meshes — a fresh
 *  function each render would make R3F re-apply the prop every render. */
const INERT_RAYCAST = () => null

type Vec3 = [number, number, number]

/** Build a flat-then-extruded geometry for one polygon (outer ring + holes). */
function polygonGeometry(polygon: Polygon): THREE.ExtrudeGeometry {
  const shape = new THREE.Shape(
    polygon.outer.map(([x, y]) => new THREE.Vector2(x, y)),
  )
  for (const hole of polygon.holes) {
    shape.holes.push(new THREE.Path(hole.map(([x, y]) => new THREE.Vector2(x, y))))
  }
  return new THREE.ExtrudeGeometry(shape, {
    depth: TERRAIN_HEIGHT,
    bevelEnabled: false,
  })
}

/** Closed loop of points for a ring, lifted to the top surface (shape space). */
function outlineLoop(ring: Point[]): Vec3[] {
  const z = TERRAIN_HEIGHT + OUTLINE_LIFT
  const loop: Vec3[] = ring.map(([x, y]) => [x, y, z])
  loop.push(loop[0])
  return loop
}

/** Bounding-box centre of a municipality in shape space — where the label sits. */
function labelAnchor(municipality: Municipality): Point {
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const polygon of municipality.polygons) {
    for (const [x, y] of polygon.outer) {
      if (x < minX) minX = x
      if (x > maxX) maxX = x
      if (y < minY) minY = y
      if (y > maxY) maxY = y
    }
  }
  return [(minX + maxX) / 2, (minY + maxY) / 2]
}

/**
 * One municipality: its extruded land part(s) and boundary outline. When
 * `active` it smoothly brightens; otherwise it smoothly settles back to the
 * normal green. Each instance animates independently.
 */
function MunicipalityPiece({
  municipality,
  active,
  interactive,
  onEnter,
  onLeave,
  onDown,
  onUp,
}: {
  municipality: Municipality
  active: boolean
  /** false for municipalities outside V1 coverage — they render as pure
   *  scenery: no hover name, no glow, no pointer affordance, no click. */
  interactive: boolean
  onEnter: (id: string) => void
  onLeave: (id: string) => void
  onDown: (event: ThreeEvent<PointerEvent>) => void
  onUp: (event: ThreeEvent<PointerEvent>, id: string) => void
}) {
  const glow = useRef(0)

  const { parts, materials, outlines } = useMemo(() => {
    const parts = municipality.polygons.map(polygonGeometry)
    const emissive = new THREE.Color(COLORS.hover)
    const cap = new THREE.MeshStandardMaterial({
      color: COLORS.land,
      roughness: 1,
      emissive,
      emissiveIntensity: 0,
    })
    const side = new THREE.MeshStandardMaterial({
      color: COLORS.landSide,
      roughness: 1,
      emissive,
      emissiveIntensity: 0,
    })
    const outlines = municipality.polygons.flatMap((polygon) => [
      outlineLoop(polygon.outer),
      ...polygon.holes.map(outlineLoop),
    ])
    return { parts, materials: [cap, side] as THREE.Material[], outlines }
  }, [municipality])

  useEffect(() => {
    return () => {
      parts.forEach((geometry) => geometry.dispose())
      materials.forEach((material) => material.dispose())
    }
  }, [parts, materials])

  // supported municipalities keep a faint glow at rest so they read as the
  // available choices; everyone else settles fully back to plain green.
  const restGlow = interactive ? REST_GLOW : 0

  useFrame((_, delta) => {
    const target = active ? 1 : restGlow
    if (glow.current === target && target === 0) return

    const k = 1 - Math.exp(-delta * HOVER_LERP_RATE)
    glow.current = THREE.MathUtils.lerp(glow.current, target, k)
    if (!active && Math.abs(glow.current - restGlow) < 0.002) glow.current = restGlow

    const cap = materials[0] as THREE.MeshStandardMaterial
    const side = materials[1] as THREE.MeshStandardMaterial
    cap.emissiveIntensity = glow.current * HOVER_EMISSIVE
    side.emissiveIntensity = glow.current * HOVER_EMISSIVE * 0.6
  })

  const handlers = interactive
    ? {
        onPointerOver: (event: ThreeEvent<PointerEvent>) => {
          event.stopPropagation()
          onEnter(municipality.id)
        },
        onPointerMove: () => onEnter(municipality.id),
        onPointerOut: () => onLeave(municipality.id),
        onPointerDown: onDown,
        onPointerUp: (event: ThreeEvent<PointerEvent>) => onUp(event, municipality.id),
      }
    : {}

  return (
    <group {...handlers}>
      {parts.map((geometry, index) => (
        <mesh
          key={index}
          name={municipality.id}
          geometry={geometry}
          material={materials}
          castShadow
          receiveShadow
          // inert pieces are invisible to the raycaster (they also carry no
          // pointer handlers) -> no hover, no cursor, no click.
          raycast={interactive ? undefined : INERT_RAYCAST}
        />
      ))}

      {outlines.map((points, index) => (
        <Line
          key={`outline-${index}`}
          points={points}
          color={interactive ? COLORS.hover : COLORS.border}
          lineWidth={interactive ? 2.4 : 1.25}
          transparent
          opacity={interactive ? 0.95 : 0.82}
          polygonOffset
          polygonOffsetFactor={-2}
        />
      ))}
    </group>
  )
}

/**
 * An always-visible, clickable name tag floating over a supported municipality.
 * Clicking it runs the exact same selection flow as clicking the land itself.
 */
function SupportedLabel({
  municipality,
  onSelect,
}: {
  municipality: Municipality
  onSelect?: (id: string) => void
}) {
  const anchor = useMemo(() => labelAnchor(municipality), [municipality])

  return (
    <Html
      position={[anchor[0], anchor[1], TERRAIN_HEIGHT + LABEL_LIFT]}
      center
      wrapperClass="municipality-label-wrap"
      style={{ pointerEvents: 'auto' }}
      zIndexRange={[24, 0]}
    >
      <button
        type="button"
        className="municipality-choice"
        onClick={() => onSelect?.(municipality.id)}
      >
        <span className="municipality-choice__name">{municipality.name}</span>
        <span className="municipality-choice__hint">Click to choose</span>
      </button>
    </Html>
  )
}

/**
 * All Metro Vancouver municipalities, drawn together in their real-world
 * relative positions as simple extruded green land, each with a thin boundary
 * outline. Only the V1-supported ones (Vancouver / Burnaby / Surrey) are
 * interactive — highlighted, hover-brightened, and carrying an always-visible
 * clickable name tag. Every other municipality is inert scenery.
 *
 * The data is authored in a 2D map plane (+x East, +y North). The whole
 * group is laid flat (rotate -90° about X, so North points into -Z) and
 * dropped so every piece's top surface sits at y = 0.
 */
export function Municipalities({
  interactive = true,
  chooserActive = true,
  onSelect,
}: {
  interactive?: boolean
  /** Show the always-visible choice tags — true only while no place is chosen. */
  chooserActive?: boolean
  /** Fired on a genuine click (not a drag) of a municipality or its tag. */
  onSelect?: (id: string) => void
}) {
  const [hoveredId, setHoveredId] = useState<string | null>(null)

  // Pointer-down screen position + time, so a drag-to-rotate is not mistaken
  // for a click-to-select.
  const pointerDown = useRef<{ x: number; y: number; t: number } | null>(null)

  const enter = (id: string) => {
    if (!interactive) return
    setHoveredId(id)
  }
  const leave = (id: string) => {
    setHoveredId((current) => (current === id ? null : current))
  }

  const handleDown = (event: ThreeEvent<PointerEvent>) => {
    pointerDown.current = {
      x: event.nativeEvent.clientX,
      y: event.nativeEvent.clientY,
      t: performance.now(),
    }
  }
  const handleUp = (event: ThreeEvent<PointerEvent>, id: string) => {
    const start = pointerDown.current
    pointerDown.current = null
    if (!start) return
    const moved = Math.hypot(
      event.nativeEvent.clientX - start.x,
      event.nativeEvent.clientY - start.y,
    )
    if (moved < 6 && performance.now() - start.t < 700) {
      onSelect?.(id)
    }
  }

  const activeId = interactive ? hoveredId : null

  return (
    <group rotation={[-Math.PI / 2, 0, 0]} position={[0, -TERRAIN_HEIGHT, 0]}>
      {municipalities.map((municipality) => (
        <MunicipalityPiece
          key={municipality.id}
          municipality={municipality}
          active={activeId === municipality.id}
          // Coverage gate ONLY — a stable value. It must NOT depend on the
          // transient `interactive` flag (orbiting/zooming): OrbitControls fires
          // its `start` event on pointer-down, which would tear the click
          // handlers off a supported piece before pointer-up and the click would
          // never reach `onSelect`. `interactive` still suppresses hover glow
          // for everyone via `enter()` + `activeId`.
          interactive={isSupportedMunicipality(municipality.id)}
          onEnter={enter}
          onLeave={leave}
          onDown={handleDown}
          onUp={handleUp}
        />
      ))}

      {chooserActive &&
        municipalities
          .filter((m) => isSupportedMunicipality(m.id))
          .map((municipality) => (
            <SupportedLabel
              key={`label-${municipality.id}`}
              municipality={municipality}
              onSelect={onSelect}
            />
          ))}
    </group>
  )
}
