import { useMemo } from 'react'
import { Instance, Instances } from '@react-three/drei'
import { ignoreRaycast } from './common'
import type { BuildingInstance } from './scatter'

/**
 * All buildings on the map, drawn with three instanced meshes (bodies, flat
 * roofs, pyramid roofs) — a handful of draw calls for the whole city.
 * Decorative only — ignores pointer events, so hover still hits the
 * municipality underneath.
 */
export function BuildingField({ items }: { items: BuildingInstance[] }) {
  const flatRoofs = useMemo(() => items.filter((b) => b.roof === 'flat'), [items])
  const pyramidRoofs = useMemo(
    () => items.filter((b) => b.roof === 'pyramid'),
    [items],
  )

  return (
    <group>
      <Instances limit={items.length} castShadow receiveShadow raycast={ignoreRaycast}>
        <boxGeometry />
        <meshStandardMaterial flatShading roughness={0.85} />
        {items.map((b, i) => (
          <Instance
            key={i}
            position={[b.position[0], b.height / 2, b.position[2]]}
            rotation={[0, b.rotation, 0]}
            scale={[b.width, b.height, b.depth]}
            color={b.colorHex}
          />
        ))}
      </Instances>

      {flatRoofs.length > 0 && (
        <Instances limit={flatRoofs.length} castShadow raycast={ignoreRaycast}>
          <boxGeometry />
          <meshStandardMaterial flatShading roughness={0.8} />
          {flatRoofs.map((b, i) => (
            <Instance
              key={i}
              position={[b.position[0], b.height + 0.07, b.position[2]]}
              rotation={[0, b.rotation, 0]}
              scale={[b.width + 0.16, 0.14, b.depth + 0.16]}
              color={b.roofHex}
            />
          ))}
        </Instances>
      )}

      {pyramidRoofs.length > 0 && (
        <Instances limit={pyramidRoofs.length} castShadow raycast={ignoreRaycast}>
          <coneGeometry args={[1, 1, 4]} />
          <meshStandardMaterial flatShading roughness={0.8} />
          {pyramidRoofs.map((b, i) => {
            const span = Math.max(b.width, b.depth) * 0.72
            const rise = Math.min(b.width, b.depth) * 0.6
            return (
              <Instance
                key={i}
                position={[b.position[0], b.height + rise / 2, b.position[2]]}
                rotation={[0, b.rotation + Math.PI / 4, 0]}
                scale={[span, rise, span]}
                color={b.roofHex}
              />
            )
          })}
        </Instances>
      )}
    </group>
  )
}
