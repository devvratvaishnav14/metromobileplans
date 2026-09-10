import type { XZ } from './geo'

/**
 * A few named park / green areas across the map. World XZ + radius.
 *
 * Data only. `Parks.tsx` draws the lawn; `scatter.ts` reads these to drop a
 * denser cluster of trees over each one.
 */
export interface Park {
  id: string
  centre: XZ
  radius: number
  /** Roughly how many trees to cluster here. */
  trees: number
}

export const PARKS: Park[] = [
  { id: 'stanley', centre: [-15.4, -5.1], radius: 2.3, trees: 16 },
  { id: 'queen-elizabeth', centre: [-11, -1.4], radius: 1.4, trees: 9 },
  { id: 'central-burnaby', centre: [-6.4, -2.9], radius: 1.7, trees: 11 },
  { id: 'surrey-green', centre: [3.4, 5.6], radius: 1.9, trees: 12 },
  { id: 'delta-flats', centre: [-7.6, 7.2], radius: 1.6, trees: 9 },
  { id: 'coquitlam-park', centre: [3.4, -3.4], radius: 1.4, trees: 8 },
]
