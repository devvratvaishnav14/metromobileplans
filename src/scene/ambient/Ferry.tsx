import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { WATER } from '../config'
import { ignoreRaycast } from '../scenery/common'
import type { FerryRoute } from './ferryRoutes'

/**
 * One tiny stylised ferry looping slowly along its route in the open water.
 * Ambient decoration — never touches land, never intercepts pointer events.
 */
export function Ferry({ route }: { route: FerryRoute }) {
  const group = useRef<THREE.Group>(null)
  const bobPhase = route.offset * Math.PI * 2

  const curve = useMemo(
    () =>
      new THREE.CatmullRomCurve3(
        route.path.map(([x, z]) => new THREE.Vector3(x, 0, z)),
        true,
        'catmullrom',
        0.4,
      ),
    [route.path],
  )

  useFrame((frameState) => {
    if (!group.current) return
    const clock = frameState.clock.elapsedTime
    const raw =
      route.offset + (route.direction * clock) / route.loopSeconds
    const t = ((raw % 1) + 1) % 1

    const pos = curve.getPointAt(t)
    const tan = curve.getTangentAt(t).multiplyScalar(route.direction)

    group.current.position.set(
      pos.x,
      WATER.y + 0.16 + Math.sin(clock * 1.3 + bobPhase) * 0.03,
      pos.z,
    )
    group.current.rotation.y = Math.atan2(tan.x, tan.z)
    group.current.rotation.z = Math.sin(clock * 1.0 + bobPhase) * 0.03
  })

  return (
    <group ref={group}>
      <group scale={route.scale}>
        {/* hull */}
        <mesh position={[0, 0.16, 0]} castShadow raycast={ignoreRaycast}>
          <boxGeometry args={[0.72, 0.32, 1.9]} />
          <meshStandardMaterial color="#f2efe6" roughness={0.8} flatShading />
        </mesh>
        {/* hull stripe */}
        <mesh position={[0, 0.03, 0]} raycast={ignoreRaycast}>
          <boxGeometry args={[0.76, 0.14, 1.94]} />
          <meshStandardMaterial color="#3f7fb0" roughness={0.8} flatShading />
        </mesh>
        {/* superstructure */}
        <mesh position={[0, 0.44, -0.15]} castShadow raycast={ignoreRaycast}>
          <boxGeometry args={[0.52, 0.3, 1.0]} />
          <meshStandardMaterial color="#e7dcc4" roughness={0.85} flatShading />
        </mesh>
        {/* funnel */}
        <mesh position={[0, 0.66, -0.4]} castShadow raycast={ignoreRaycast}>
          <cylinderGeometry args={[0.08, 0.09, 0.24, 8]} />
          <meshStandardMaterial color="#c8564a" roughness={0.85} flatShading />
        </mesh>
      </group>
    </group>
  )
}
