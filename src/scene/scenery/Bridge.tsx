import { PALETTE, ignoreRaycast } from './common'
import type { XZ } from './geo'

export interface BridgeProps {
  from: XZ
  to: XZ
  width?: number
}

/**
 * A stylised miniature bridge deck carrying a road across a water gap: a flat
 * deck with cream railings and a few piers dropping into the water. Decorative
 * only — ignores pointer events.
 */
export function Bridge({ from, to, width = 1.5 }: BridgeProps) {
  const [ax, az] = from
  const [bx, bz] = to
  const length = Math.hypot(bx - ax, bz - az) + 0.8
  const angle = Math.atan2(bz - az, bx - ax)
  const deckY = 0.28

  return (
    <group position={[(ax + bx) / 2, 0, (az + bz) / 2]} rotation={[0, -angle, 0]}>
      <mesh position={[0, deckY, 0]} castShadow receiveShadow raycast={ignoreRaycast}>
        <boxGeometry args={[length, 0.16, width]} />
        <meshStandardMaterial color={PALETTE.roadEdge} roughness={0.9} />
      </mesh>

      <mesh position={[0, deckY + 0.11, 0]} receiveShadow raycast={ignoreRaycast}>
        <boxGeometry args={[length, 0.05, width - 0.3]} />
        <meshStandardMaterial color={PALETTE.road} roughness={0.7} />
      </mesh>

      {[-1, 1].map((side) => (
        <mesh
          key={side}
          position={[0, deckY + 0.17, side * (width / 2 - 0.05)]}
          castShadow
          raycast={ignoreRaycast}
        >
          <boxGeometry args={[length, 0.2, 0.09]} />
          <meshStandardMaterial color={PALETTE.roof.cream} roughness={0.85} />
        </mesh>
      ))}

      {[-0.34, 0, 0.34].map((t) => (
        <mesh
          key={t}
          position={[t * length, -0.7, 0]}
          castShadow
          raycast={ignoreRaycast}
        >
          <boxGeometry args={[0.28, 2.3, 0.28]} />
          <meshStandardMaterial color={PALETTE.roadEdge} roughness={0.95} />
        </mesh>
      ))}
    </group>
  )
}
