/**
 * Soft, playful lighting for a miniature-world look:
 * - hemisphere light tints fill light sky-blue from above, green from below
 * - ambient lifts the shadows so nothing goes fully black
 * - one warm directional "sun" gives the land depth and a soft cast shadow
 */
export function Lights() {
  return (
    <>
      <hemisphereLight args={['#cdeaff', '#6fae5a', 0.7]} />
      <ambientLight intensity={0.35} />
      <directionalLight
        position={[10, 14, 8]}
        intensity={2.4}
        color="#fff4e0"
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-radius={6}
        shadow-bias={-0.0002}
        shadow-camera-left={-20}
        shadow-camera-right={20}
        shadow-camera-top={20}
        shadow-camera-bottom={-20}
        shadow-camera-near={0.5}
        shadow-camera-far={60}
      />
    </>
  )
}
