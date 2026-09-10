import { useEffect, useRef, useState, type RefObject } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { Character } from './Character'
import { CharacterSpeech } from './CharacterSpeech'
import { type CharacterState } from './characterConfig'
import { NAV_GRAPH, START_NODE } from '../navigation/navGraph'
import { DESTINATIONS } from '../navigation/destinations'
import { routeFrom } from '../navigation/pathfind'

const CRUISE_SPEED = 3.4 // world units / second — brisk purposeful walk
const TURN_RATE = 7.0 // radians / second
const WAYPOINT_EPS = 0.16 // close enough -> advance to next waypoint
const SLOWDOWN_DIST = 2.2 // start decelerating this far from the final point
const ARRIVE_SPEED = 0.4 // floor speed during the final approach

/** Shortest signed angle from a to b, in (-PI, PI]. */
function angleDelta(a: number, b: number) {
  return ((b - a + Math.PI * 3) % (Math.PI * 2)) - Math.PI
}

interface Props {
  /** Municipality id the user last clicked, or null. */
  destinationId: string | null
  /** Reports the active route (world waypoints) so the overlay can draw it. */
  onRoute?: (route: THREE.Vector3[] | null) => void
  /** Written every frame with his live world position (for the route overlay). */
  positionRef?: RefObject<THREE.Vector3>
  /** Written every frame with distance travelled along the current route. */
  progressRef?: RefObject<number>
  /** Called once when he reaches the end of the current route. */
  onArrive?: () => void
  /** "[Place] it is." line to show in a bubble above him, or null. */
  speechText?: string | null
}

/**
 * Owns the boy's world placement, routing and animation state.
 *
 *   - starts exactly on nav node START_NODE, in IDLE/PHONE
 *   - clicking a municipality routes from his current position over the hidden
 *     road graph to that municipality's anchor node
 *   - every frame we physically translate the wrapper group along the route
 *     (delta-time based) and turn him to face travel; the skeletal WALK clip
 *     only animates his body
 *   - approaching the end he decelerates, stops, and crossfades to IDLE/PHONE
 */
export function CharacterController({
  destinationId,
  onRoute,
  positionRef,
  progressRef,
  onArrive,
  speechText,
}: Props) {
  const [animState, setAnimState] = useState<CharacterState>('idle')

  const group = useRef<THREE.Group>(null)
  const pos = useRef(
    new THREE.Vector3(
      NAV_GRAPH.nodes[START_NODE][0],
      0,
      NAV_GRAPH.nodes[START_NODE][1],
    ),
  )
  const yaw = useRef(2.3)
  const speed = useRef(0)
  const path = useRef<THREE.Vector3[] | null>(null)
  const leg = useRef(0)

  // A municipality was clicked -> route from where he is right now.
  useEffect(() => {
    if (!destinationId) return
    const dest = DESTINATIONS[destinationId]
    if (!dest) return

    const route = routeFrom(pos.current.x, pos.current.z, dest.node)
    if (route.length < 2) return

    path.current = route
    leg.current = 1 // waypoint 0 is his current position
    if (progressRef) progressRef.current = 0
    setAnimState('walk')
    onRoute?.(route)

    let len = 0
    for (let i = 1; i < route.length; i++) len += route[i].distanceTo(route[i - 1])
    console.log(
      `[nav] -> ${dest.name}  (${route.length} waypoints, ${len.toFixed(0)}u)`,
    )
  }, [destinationId, onRoute, progressRef])

  useFrame((_, dtRaw) => {
    const g = group.current
    if (!g) return
    // clamp only against a real hitch (tab switch, GC pause); normal low frame
    // rates should still translate him the correct distance
    const dt = Math.min(dtRaw, 0.1)

    const route = path.current
    if (route && leg.current < route.length) {
      const target = route[leg.current]
      const dir = new THREE.Vector3(
        target.x - pos.current.x,
        0,
        target.z - pos.current.z,
      )
      const dist = dir.length()
      if (dist > 1e-5) dir.normalize()

      // turn toward the direction of travel
      const desiredYaw = Math.atan2(dir.x, dir.z)
      const dYaw = angleDelta(yaw.current, desiredYaw)
      yaw.current += Math.sign(dYaw) * Math.min(Math.abs(dYaw), TURN_RATE * dt)

      // distance still to run to the end of the route
      let toEnd = dist
      for (let i = leg.current + 1; i < route.length; i++) {
        toEnd += route[i].distanceTo(route[i - 1])
      }

      // speed target: cruise, easing down only for genuine sharp turns and
      // near the end
      let want = CRUISE_SPEED
      const turn = Math.abs(dYaw)
      if (turn > 0.5) want *= THREE.MathUtils.clamp(1 - (turn - 0.5) * 0.8, 0.4, 1)
      if (toEnd < SLOWDOWN_DIST) {
        want = Math.max(ARRIVE_SPEED, want * (toEnd / SLOWDOWN_DIST))
      }
      speed.current += (want - speed.current) * (1 - Math.exp(-dt * 9))

      const stepLen = Math.min(speed.current * dt, dist)
      pos.current.x += dir.x * stepLen
      pos.current.z += dir.z * stepLen
      if (progressRef) progressRef.current += stepLen

      if (dist - stepLen < WAYPOINT_EPS) {
        leg.current += 1
        if (leg.current >= route.length) {
          path.current = null
          speed.current = 0
          setAnimState('idle')
          onRoute?.(null)
          onArrive?.()
          console.log(
            `[nav] arrived  [${pos.current.x.toFixed(1)}, ${pos.current.z.toFixed(1)}]`,
          )
        }
      }
    } else if (speed.current !== 0) {
      speed.current = 0
    }

    g.position.set(pos.current.x, 0, pos.current.z)
    g.rotation.y = yaw.current
    positionRef?.current?.set(pos.current.x, 0, pos.current.z)
  })

  return (
    <group ref={group}>
      <Character state={animState} moveSpeed={speed} />
      <CharacterSpeech text={speechText ?? null} />
    </group>
  )
}
