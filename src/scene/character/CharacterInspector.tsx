import { useEffect, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { COLORS } from '../config'
import { Character } from './Character'
import { CHARACTER_HEIGHT, type CharacterState } from './characterConfig'

/**
 * DEV-ONLY close-up inspector for the boy. Not part of the app — reached by
 * opening `/#inspect-character`. Lets us check the model + both animation
 * states from any angle at close range. Uses the same lighting rig as the
 * main scene.
 */
export function CharacterInspector() {
  const [state, setState] = useState<CharacterState>('idle')

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === 'g') {
        setState((s) => (s === 'idle' ? 'walk' : 'idle'))
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <Canvas
      shadows="soft"
      dpr={[1, 2]}
      camera={{ position: [0.9, CHARACTER_HEIGHT * 0.8, 1.3], fov: 30 }}
      style={{ position: 'absolute', inset: 0 }}
    >
      <color attach="background" args={[COLORS.background]} />
      <hemisphereLight args={['#cdeaff', '#6fae5a', 0.7]} />
      <ambientLight intensity={0.35} />
      <directionalLight
        position={[2.5, 4, 2]}
        intensity={2.4}
        color="#fff4e0"
        castShadow
        shadow-mapSize={[1024, 1024]}
      />

      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <circleGeometry args={[3, 40]} />
        <meshStandardMaterial color={COLORS.land} roughness={1} />
      </mesh>

      <Character state={state} />

      <OrbitControls
        makeDefault
        enableDamping
        target={[0, CHARACTER_HEIGHT * 0.55, 0]}
        minDistance={0.6}
        maxDistance={6}
      />
    </Canvas>
  )
}
