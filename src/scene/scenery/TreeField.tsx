import { useMemo } from 'react'
import { Instance, Instances } from '@react-three/drei'
import { PALETTE, ignoreRaycast } from './common'
import type { TreeInstance } from './scatter'

/**
 * All trees on the map, drawn with instanced meshes (trunks + two crown
 * shapes). Decorative only — ignores pointer events.
 */
export function TreeField({ items }: { items: TreeInstance[] }) {
  const leafy = useMemo(() => items.filter((t) => t.variant === 'leafy'), [items])
  const conifer = useMemo(
    () => items.filter((t) => t.variant === 'conifer'),
    [items],
  )

  return (
    <group>
      {items.length > 0 && (
        <Instances limit={items.length} castShadow raycast={ignoreRaycast}>
          <cylinderGeometry args={[0.11, 0.13, 1, 6]} />
          <meshStandardMaterial color={PALETTE.trunk} roughness={1} flatShading />
          {items.map((t, i) => (
            <Instance
              key={i}
              position={[t.position[0], 0.35 * t.scale, t.position[2]]}
              scale={[t.scale, 0.7 * t.scale, t.scale]}
            />
          ))}
        </Instances>
      )}

      {leafy.length > 0 && (
        <Instances limit={leafy.length} castShadow raycast={ignoreRaycast}>
          <icosahedronGeometry args={[0.6, 1]} />
          <meshStandardMaterial roughness={0.9} flatShading />
          {leafy.map((t, i) => (
            <Instance
              key={i}
              position={[t.position[0], 1.12 * t.scale, t.position[2]]}
              rotation={[0, t.rotation, 0]}
              scale={t.scale}
              color={t.colorHex}
            />
          ))}
        </Instances>
      )}

      {conifer.length > 0 && (
        <Instances limit={conifer.length} castShadow raycast={ignoreRaycast}>
          <coneGeometry args={[0.5, 1.5, 7]} />
          <meshStandardMaterial roughness={0.9} flatShading />
          {conifer.map((t, i) => (
            <Instance
              key={i}
              position={[t.position[0], 1.25 * t.scale, t.position[2]]}
              rotation={[0, t.rotation, 0]}
              scale={t.scale}
              color={t.colorHex}
            />
          ))}
        </Instances>
      )}
    </group>
  )
}
