import type { XZ } from '../scenery/geo'

/**
 * Looping ferry routes, world XZ. Every point (and the smoothed curve between
 * them) was checked against the municipality shapes — all water, never land.
 *
 * Timing is deliberately desynchronised: different loop durations, start
 * offsets, and travel directions so the boats never look choreographed.
 * Data only — `Ferries.tsx` renders it.
 */
export interface FerryRoute {
  id: string
  /** Closed loop of waypoints. */
  path: XZ[]
  /** Seconds for one full loop (slow, ambient). */
  loopSeconds: number
  /** 0..1 phase offset along the loop at t = 0. */
  offset: number
  /** Direction of travel along the path. */
  direction: 1 | -1
  /** Small size variation between boats. */
  scale: number
}

export const FERRY_ROUTES: FerryRoute[] = [
  {
    id: 'south-strait',
    path: [
      [-13, 15.8],
      [3, 15.3],
      [5.6, 16.7],
      [3, 18.5],
      [-13, 18.9],
      [-15.6, 17.3],
    ],
    loopSeconds: 96,
    offset: 0.12,
    direction: 1,
    scale: 1.0,
  },
  {
    id: 'west-passage',
    path: [
      [-22, -7],
      [-25, 0],
      [-24, 8],
      [-21, 2],
      [-20, -6],
    ],
    loopSeconds: 132,
    offset: 0.57,
    direction: -1,
    scale: 0.88,
  },
  {
    id: 'boundary-bay',
    path: [
      [5, 15.6],
      [12, 15.2],
      [15.4, 16.6],
      [12, 18.2],
      [5, 18],
    ],
    loopSeconds: 81,
    offset: 0.82,
    direction: 1,
    scale: 0.82,
  },
  {
    id: 'north-inlet',
    path: [
      [-11, -14.9],
      [0, -14.5],
      [9, -15],
      [1, -16.1],
      [-11, -16.1],
    ],
    loopSeconds: 154,
    offset: 0.33,
    direction: -1,
    scale: 1.05,
  },
]
