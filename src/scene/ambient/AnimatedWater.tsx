import { useCallback, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { COLORS, WATER } from '../config'
import { ignoreRaycast } from '../scenery/common'

/**
 * Stylised miniature-world water: one large plane with gentle rolling waves and
 * a slow tonal shift, done entirely on the GPU — a few sine waves injected into
 * a MeshStandardMaterial (so scene lighting and shadows still apply) plus a
 * matching normal tweak for a soft shimmer. Cheap and calm, not a simulation.
 *
 * Decorative — ignores pointer events.
 */
export function AnimatedWater() {
  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uDeep: { value: new THREE.Color(COLORS.waterDeep) },
    }),
    [],
  )

  const onBeforeCompile = useCallback(
    (shader: THREE.WebGLProgramParametersWithUniforms) => {
      shader.uniforms.uTime = uniforms.uTime
      shader.uniforms.uDeep = uniforms.uDeep

      shader.vertexShader = ('uniform float uTime;\nvarying vec2 vWavePos;\n' +
        shader.vertexShader)
        .replace(
          '#include <beginnormal_vertex>',
          `#include <beginnormal_vertex>
           {
             vec2 wp = position.xy;
             float gx = 0.030 * cos(wp.x * 0.30 + uTime * 0.70)
                      + 0.011 * cos((wp.x + wp.y) * 0.22 + uTime * 0.90);
             float gy = 0.029 * cos(wp.y * 0.42 - uTime * 0.55)
                      + 0.011 * cos((wp.x + wp.y) * 0.22 + uTime * 0.90);
             objectNormal = normalize(vec3(-gx, -gy, 1.0));
           }`,
        )
        .replace(
          '#include <begin_vertex>',
          `#include <begin_vertex>
           vWavePos = position.xy;
           transformed.z += sin(position.x * 0.30 + uTime * 0.70) * 0.10
                          + sin(position.y * 0.42 - uTime * 0.55) * 0.07
                          + sin((position.x + position.y) * 0.22 + uTime * 0.90) * 0.05;`,
        )

      shader.fragmentShader = (
        'uniform float uTime;\nuniform vec3 uDeep;\nvarying vec2 vWavePos;\n' +
        shader.fragmentShader
      ).replace(
        '#include <color_fragment>',
        `#include <color_fragment>
         float tone = (sin(vWavePos.x * 0.08 + uTime * 0.15) * 0.5 + 0.5)
                    * (sin(vWavePos.y * 0.06 - uTime * 0.12) * 0.5 + 0.5);
         diffuseColor.rgb = mix(diffuseColor.rgb, uDeep, tone * 0.22);`,
      )
    },
    [uniforms],
  )

  useFrame((_, delta) => {
    uniforms.uTime.value += delta
  })

  return (
    <mesh
      position={[0, WATER.y, 0]}
      rotation={[-Math.PI / 2, 0, 0]}
      receiveShadow
      raycast={ignoreRaycast}
    >
      <planeGeometry
        args={[WATER.size, WATER.size, WATER.segments, WATER.segments]}
      />
      <meshStandardMaterial
        color={COLORS.water}
        roughness={0.52}
        metalness={0}
        onBeforeCompile={onBeforeCompile}
      />
    </mesh>
  )
}
