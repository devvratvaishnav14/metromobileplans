import { ignoreRaycast } from './common'
import { PARKS } from './park-data'

/**
 * Lawn discs for the named park areas. The denser tree cluster over each park
 * is produced by the scatter generator (see `scatter.ts`). Decorative only.
 */
export function Parks() {
  return (
    <group>
      {PARKS.map((park) => (
        <mesh
          key={park.id}
          position={[park.centre[0], 0.02, park.centre[1]]}
          rotation={[-Math.PI / 2, 0, 0]}
          receiveShadow
          raycast={ignoreRaycast}
        >
          <circleGeometry args={[park.radius, 30]} />
          <meshStandardMaterial color="#7cc069" roughness={1} />
        </mesh>
      ))}
    </group>
  )
}
