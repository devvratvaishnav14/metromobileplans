import { PALETTE, ignoreRaycast } from './common'

export interface MountainProps {
  position: [number, number, number]
  height: number
  radius: number
  /** Index into the mountain-green palette. */
  tone?: number
  rotation?: number
  /** Add a smaller secondary peak beside the main one for a ridge silhouette. */
  ridge?: boolean
}

/**
 * A stylised low-poly mountain form: a faceted, gently belted green cone that
 * rises out of the map, topped with a lighter rocky cap, optionally with a
 * smaller secondary peak. Not real elevation data — a miniature-world stand-in
 * for the eventual North Shore mountains. Decorative only — ignores pointer
 * events.
 */
export function Mountain({
  position,
  height,
  radius,
  tone = 0,
  rotation = 0,
  ridge = false,
}: MountainProps) {
  const green = PALETTE.mountain[tone % PALETTE.mountain.length]
  const green2 = PALETTE.mountain[(tone + 2) % PALETTE.mountain.length]
  // Sink the base slightly so the mountain grows out of the ground.
  const sink = 0.4
  const capHeight = height * 0.32

  return (
    <group position={position} rotation={[0, rotation, 0]}>
      <mesh
        position={[0, height / 2 - sink, 0]}
        castShadow
        receiveShadow
        raycast={ignoreRaycast}
      >
        <coneGeometry args={[radius, height, 6, 2]} />
        <meshStandardMaterial color={green} roughness={1} flatShading />
      </mesh>

      <mesh
        position={[0, height - sink - capHeight / 2, 0]}
        castShadow
        raycast={ignoreRaycast}
      >
        <coneGeometry args={[radius * 0.34, capHeight, 6, 1]} />
        <meshStandardMaterial color={PALETTE.mountainRock} roughness={1} flatShading />
      </mesh>

      {ridge && (
        <mesh
          position={[radius * 0.82, (height * 0.66) / 2 - sink, radius * 0.28]}
          castShadow
          receiveShadow
          raycast={ignoreRaycast}
        >
          <coneGeometry args={[radius * 0.68, height * 0.66, 6, 2]} />
          <meshStandardMaterial color={green2} roughness={1} flatShading />
        </mesh>
      )}
    </group>
  )
}
