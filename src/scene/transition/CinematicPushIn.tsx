import { useRef, type RefObject } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { CAMERA } from '../config'

interface Props {
  /** Run the dive while true. */
  active: boolean
  /** World-space centre of the selected municipality. */
  target: RefObject<THREE.Vector3>
  /** Written with the target's screen position (0-100 %) for the DOM wash origin. */
  focusRef: RefObject<{ x: number; y: number }>
}

/** How close (world units) the camera ends up to the municipality centre. The
 *  DOM wash covers the final stretch and the swap to the analysis view. */
const END_DISTANCE = 6.5

/**
 * A fast, exaggerated camera dive from the map framing straight toward the
 * selected municipality once the user confirms. Takes the camera off
 * OrbitControls, eases it in hard (with a slight FOV narrowing for a
 * dolly-zoom kick), and reports the target's screen position so the DOM
 * `CinematicTransition` wash can bloom from the right spot. Restores the
 * camera + controls if it is switched off without completing.
 */
export function CinematicPushIn({ active, target, focusRef }: Props) {
  const { camera, controls } = useThree()
  const started = useRef(false)
  const t = useRef(0)
  const from = useRef(new THREE.Vector3())
  const look = useRef(new THREE.Vector3())

  useFrame((_, dt) => {
    if (!active) {
      if (started.current) {
        const c = controls as { enabled?: boolean } | null
        if (c) c.enabled = true
        const cam = camera as THREE.PerspectiveCamera
        if (cam.fov !== CAMERA.fov) {
          cam.fov = CAMERA.fov
          cam.updateProjectionMatrix()
        }
      }
      started.current = false
      t.current = 0
      return
    }

    if (!started.current) {
      started.current = true
      t.current = 0
      from.current.copy(camera.position)
      const c = controls as { enabled?: boolean } | null
      if (c) c.enabled = false
    }

    t.current = Math.min(1, t.current + dt / 0.85)
    const ease = Math.pow(t.current, 1.8) // slow start, hard rush
    const smooth = t.current * t.current * (3 - 2 * t.current)

    look.current.copy(target.current)

    // fly from the start position straight at the municipality, closing in
    const dir = from.current.clone().sub(look.current).normalize()
    const closeDist = THREE.MathUtils.lerp(
      from.current.distanceTo(look.current),
      END_DISTANCE,
      ease,
    )
    const desired = look.current.clone().addScaledVector(dir, closeDist)
    camera.position.lerpVectors(from.current, desired, ease)
    camera.lookAt(look.current)

    const cam = camera as THREE.PerspectiveCamera
    cam.fov = THREE.MathUtils.lerp(CAMERA.fov, CAMERA.fov * 0.72, smooth)
    cam.updateProjectionMatrix()

    const p = look.current.clone().project(camera)
    if (focusRef.current) {
      focusRef.current.x = THREE.MathUtils.clamp((p.x * 0.5 + 0.5) * 100, 0, 100)
      focusRef.current.y = THREE.MathUtils.clamp((-p.y * 0.5 + 0.5) * 100, 0, 100)
    }
  })

  return null
}
