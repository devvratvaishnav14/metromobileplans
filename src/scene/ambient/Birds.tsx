import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { ignoreRaycast } from '../scenery/common'

/**
 * A few small birds drifting in slow circles high above the map — ambient life,
 * not a flock. Low-poly two-triangle wings with a gentle flap. Decorative.
 */

interface BirdSpec {
  centre: [number, number]
  radius: number
  height: number
  /** Loops per second (sign sets direction). */
  speed: number
  phase: number
  flap: number
}

const BIRDS: BirdSpec[] = [
  { centre: [-5, -3], radius: 6.5, height: 12, speed: 0.045, phase: 0, flap: 5.5 },
  { centre: [5, 3], radius: 8, height: 14, speed: -0.033, phase: 2.2, flap: 4.8 },
  { centre: [-11, 5], radius: 5, height: 10.5, speed: 0.052, phase: 4.1, flap: 6.2 },
]

function Bird({ spec }: { spec: BirdSpec }) {
  const group = useRef<THREE.Group>(null)
  const leftWing = useRef<THREE.Group>(null)
  const rightWing = useRef<THREE.Group>(null)

  useFrame((state) => {
    const time = state.clock.elapsedTime
    const a = spec.phase + time * spec.speed * Math.PI * 2

    if (group.current) {
      group.current.position.set(
        spec.centre[0] + Math.cos(a) * spec.radius,
        spec.height + Math.sin(time * 0.6 + spec.phase) * 0.35,
        spec.centre[1] + Math.sin(a) * spec.radius,
      )
      // face along the tangent of the circle
      group.current.rotation.y = -a + (spec.speed > 0 ? -Math.PI / 2 : Math.PI / 2)
    }
    const flap = Math.sin(time * spec.flap + spec.phase) * 0.45
    if (leftWing.current) leftWing.current.rotation.z = 0.16 + flap
    if (rightWing.current) rightWing.current.rotation.z = -0.16 - flap
  })

  return (
    <group ref={group} scale={0.9}>
      <group ref={leftWing}>
        <mesh position={[-0.28, 0, 0]} raycast={ignoreRaycast}>
          <boxGeometry args={[0.55, 0.03, 0.18]} />
          <meshStandardMaterial color="#414652" roughness={1} flatShading />
        </mesh>
      </group>
      <group ref={rightWing}>
        <mesh position={[0.28, 0, 0]} raycast={ignoreRaycast}>
          <boxGeometry args={[0.55, 0.03, 0.18]} />
          <meshStandardMaterial color="#414652" roughness={1} flatShading />
        </mesh>
      </group>
    </group>
  )
}

export function Birds() {
  return (
    <group>
      {BIRDS.map((spec, i) => (
        <Bird key={i} spec={spec} />
      ))}
    </group>
  )
}
