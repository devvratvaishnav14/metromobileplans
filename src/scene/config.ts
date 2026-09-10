/**
 * Central place for scene-wide constants so values stay consistent
 * as the project grows (colors, camera framing, world dimensions).
 */

export const COLORS = {
  /** Bright light-blue sky / clear color. */
  background: '#9fd4ff',
  /** Grassy green for the top of each municipality. */
  land: '#69c368',
  /** Slightly darker green for the exposed extruded sides. */
  landSide: '#4f9a54',
  /** Thin outline drawn on top of each municipality boundary. */
  border: '#234a2e',
  /** Emissive tint a municipality glows with while hovered. */
  hover: '#a6e08c',
  /** Playful cartoon blue for the water. */
  water: '#4bb8e8',
  /** Slightly deeper blue, mixed into the animated water for tonal variation. */
  waterDeep: '#3ea9dc',
} as const

/** Hover: peak emissive intensity of a municipality's top surface when pointed at. */
export const HOVER_EMISSIVE = 0.5

/** Hover: smoothing rate for the brighten / fade transition (1/seconds). */
export const HOVER_LERP_RATE = 9

export const CAMERA = {
  /**
   * High and mostly top-down with a slight tilt (~60° above the horizon)
   * so terrain depth and the sides of the land still read — a
   * strategy-game / miniature-city map view where the top surface stays
   * easy to scan and click. Framed for the full Metro Vancouver extent.
   */
  position: [6, 82, 47] as const,
  fov: 32,
} as const

/** OrbitControls limits — rotate + zoom, but never flip under the map. */
export const CONTROLS = {
  minDistance: 45,
  maxDistance: 150,
  /** Polar angle clamp: near-top-down down to a low-but-usable tilt. */
  minPolarAngle: 0.1,
  maxPolarAngle: 1.35,
  dampingFactor: 0.05,
} as const

/** Vertical thickness of the extruded municipality land pieces (scene units). */
export const TERRAIN_HEIGHT = 1.6

export const WATER = {
  /** One animated plane, large enough to run off-screen at every zoom level. */
  size: 320,
  /** Sits below the land's top so the land reads as islands in the sea. */
  y: -0.9,
  /** Grid resolution of the plane (kept modest for performance). */
  segments: 128,
} as const
