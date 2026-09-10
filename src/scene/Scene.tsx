import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import { CAMERA, COLORS, CONTROLS } from './config'
import { Lights } from './Lights'
import { Municipalities } from './Municipalities'
import { World } from './scenery/World'
import { AnimatedWater } from './ambient/AnimatedWater'
import { Ambient } from './ambient/Ambient'
import { CharacterController } from './character/CharacterController'
import { RouteOverlay } from './navigation/RouteOverlay'
import { municipalityCenter } from './navigation/municipalityFocus'
import { CinematicPushIn } from './transition/CinematicPushIn'

/** DEV-only: expose the three scene/camera/controls on `window` for tinkering
 *  and screenshot tooling. Stripped from production builds. */
function DevHandles() {
  const { scene, camera, controls } = useThree()
  if (import.meta.env.DEV) {
    Object.assign(window as unknown as Record<string, unknown>, {
      __scene: scene,
      __camera: camera,
      __controls: controls,
    })
  }
  return null
}

/**
 * Root of the 3D world. Owns the full-screen canvas, renderer settings,
 * the camera framing, and orbit controls. Individual world objects live
 * in their own components and are composed here.
 */
interface SceneProps {
  /** Municipality the character is currently routing to (set on click), or null. */
  destinationId: string | null
  /** Called when the user clicks a municipality. */
  onSelect: (id: string) => void
  /** Called once when the character reaches his destination. */
  onArrive: () => void
  /** "[Place] it is." line for his speech bubble, or null. */
  speechText: string | null
  /** Run the cinematic camera dive toward the selected municipality. */
  pushIn: boolean
  /** Shared screen-space focus point for the DOM transition wash (0-100 %). */
  focusRef: RefObject<{ x: number; y: number }>
}

export function Scene({
  destinationId,
  onSelect,
  onArrive,
  speechText,
  pushIn,
  focusRef,
}: SceneProps) {
  // Suspend municipality hover while the user is orbiting/zooming the map.
  const [orbiting, setOrbiting] = useState(false)
  // Active route + his live position, feeding the GPS route overlay.
  const [route, setRoute] = useState<THREE.Vector3[] | null>(null)
  const characterPos = useRef(new THREE.Vector3())
  const walkProgress = useRef(0)

  // World-space point the cinematic dive aims at: the selected municipality's centre.
  const diveTarget = useRef(new THREE.Vector3())
  useEffect(() => {
    if (!destinationId) return
    const c = municipalityCenter(destinationId)
    if (c) diveTarget.current.copy(c)
  }, [destinationId])

  const handleRoute = useCallback((r: THREE.Vector3[] | null) => setRoute(r), [])

  return (
    <Canvas
      shadows="soft"
      dpr={[1, 2]}
      camera={{ position: [...CAMERA.position], fov: CAMERA.fov }}
      style={{ position: 'absolute', inset: 0 }}
    >
      <color attach="background" args={[COLORS.background]} />
      <Lights />
      <AnimatedWater />
      <Municipalities interactive={!orbiting && !pushIn} onSelect={onSelect} />
      <World />
      <Ambient />
      <CharacterController
        destinationId={destinationId}
        onRoute={handleRoute}
        positionRef={characterPos}
        progressRef={walkProgress}
        onArrive={onArrive}
        speechText={speechText}
      />
      <RouteOverlay
        route={route}
        characterPos={characterPos}
        progress={walkProgress}
      />
      <CinematicPushIn
        active={pushIn}
        target={diveTarget}
        focusRef={focusRef}
      />
      <OrbitControls
        makeDefault
        enableDamping
        dampingFactor={CONTROLS.dampingFactor}
        enablePan={false}
        target={[0, 0, 0]}
        minDistance={CONTROLS.minDistance}
        maxDistance={CONTROLS.maxDistance}
        minPolarAngle={CONTROLS.minPolarAngle}
        maxPolarAngle={CONTROLS.maxPolarAngle}
        onStart={() => setOrbiting(true)}
        onEnd={() => setOrbiting(false)}
      />
      <DevHandles />
    </Canvas>
  )
}
