import type { MountainProps } from './Mountain'

/**
 * Stylised mountain layout for the northern edge of the map — the North Shore
 * ridge (West / North Vancouver) plus a couple of peaks behind Coquitlam and
 * Maple Ridge. Hand-placed on real land, world XZ, base at y = 0. Spaced out
 * so individual peaks read rather than merging into one mass.
 *
 * Data only — `Mountains.tsx` renders it, `scatter.ts` reads the footprints so
 * buildings and trees don't spawn inside a mountain.
 */
export const MOUNTAIN_RANGE: MountainProps[] = [
  // North Shore ridge, west -> east
  { position: [-16.4, 0, -11.2], height: 4.3, radius: 2.2, tone: 1, rotation: 0.3 },
  { position: [-13.4, 0, -11.8], height: 6.4, radius: 2.8, tone: 0, rotation: 0.9, ridge: true },
  { position: [-10.3, 0, -11.2], height: 5.7, radius: 2.5, tone: 2, rotation: -0.6 },
  { position: [-7.4, 0, -11.9], height: 6.8, radius: 2.9, tone: 1, rotation: 0.2, ridge: true },
  { position: [-4.6, 0, -10.8], height: 4.8, radius: 2.3, tone: 3, rotation: 1.1 },
  { position: [-8.9, 0, -9.4], height: 3.2, radius: 1.8, tone: 2, rotation: 1.7 },
  // Behind Coquitlam
  { position: [3.8, 0, -9.2], height: 4.7, radius: 2.3, tone: 1, rotation: 0.4, ridge: true },
  { position: [7.1, 0, -9.8], height: 5.3, radius: 2.5, tone: 0, rotation: -0.5 },
  // Golden Ears behind Maple Ridge
  { position: [14.2, 0, -9.1], height: 5.7, radius: 2.6, tone: 1, rotation: 0.8, ridge: true },
  { position: [16.8, 0, -9.7], height: 4.4, radius: 2.1, tone: 2, rotation: -0.3 },
]
