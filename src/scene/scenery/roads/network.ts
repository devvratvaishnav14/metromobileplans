import type { XZ } from '../geo'

/**
 * THE ROAD NETWORK — single source of truth.
 *
 * This module holds only *data*: hand-authored centre-lines that flow through
 * the real municipalities in world XZ space (map (x, y) -> world (x, -y)).
 *
 *  - `Roads.tsx` reads it to draw the decorative playmat roads and bridges.
 *  - A future navigation layer will read the SAME data to build an invisible
 *    walkable graph for the character (sample points along each path, weld
 *    near-coincident endpoints, walk the graph toward a target). That layer
 *    must depend on this file, never on the rendering components.
 *
 * Nothing here does any rendering or movement logic.
 */

export type RoadKind = 'arterial' | 'street'

export interface RoadPath {
  id: string
  kind: RoadKind
  /** Centre-line, world XZ. */
  points: XZ[]
}

export interface BridgeSpan {
  id: string
  from: XZ
  to: XZ
  width: number
}

/** Carriageway width per kind — also the clearance the nav layer should keep. */
export const ROAD_WIDTH: Record<RoadKind, number> = {
  arterial: 1.5,
  street: 0.9,
}

export const ROAD_NETWORK: RoadPath[] = [
  // ---- arterials -------------------------------------------------------------
  {
    id: 'east-west-spine',
    kind: 'arterial',
    points: [
      [-16.5, -4.4],
      [-13, -4.5],
      [-10, -4.2],
      [-7, -4],
      [-4, -3.7],
      [-1.2, -2.6],
      [2, -2.1],
      [5, -2],
      [8, -2.2],
      [11, -2.6],
      [14, -2.8],
      [17.5, -2.7],
    ],
  },
  {
    id: 'north-shore-link',
    kind: 'arterial',
    points: [
      [-9.2, -3.9],
      [-8.6, -5.4],
      [-8.7, -7.6],
      [-9.6, -9],
      [-12, -9.4],
      [-15, -9.8],
      [-17.5, -10.6],
    ],
  },
  {
    id: 'north-shore-east',
    kind: 'street',
    points: [
      [-9.6, -9],
      [-6.5, -8.4],
      [-3.5, -8.6],
      [-1.5, -7.6],
    ],
  },
  {
    id: 'south-arterial',
    kind: 'arterial',
    points: [
      [-12.4, -1],
      [-12.6, 1.8],
      [-11.6, 4.6],
      [-10.2, 7],
      [-7, 8.4],
      [-3, 8.9],
      [1, 9.4],
      [2.2, 11.6],
      [2.6, 13.6],
    ],
  },
  {
    id: 'surrey-langley',
    kind: 'arterial',
    points: [
      [-1.5, 4.6],
      [2.5, 4.1],
      [6.5, 4.4],
      [10, 5.4],
      [13.5, 6.1],
    ],
  },
  // ---- connectors ----------------------------------------------------------
  {
    id: 'vancouver-cross',
    kind: 'street',
    points: [
      [-11.4, -5.6],
      [-10.9, -2.5],
      [-10.6, 0.4],
      [-11.8, 2.4],
    ],
  },
  {
    id: 'burnaby-cross',
    kind: 'street',
    points: [
      [-5.2, -5.4],
      [-4.7, -2.4],
      [-4.3, 0.2],
    ],
  },
  {
    id: 'port-moody-loop',
    kind: 'street',
    points: [
      [-2.3, -3.6],
      [-1.2, -5.4],
      [0.9, -6.1],
      [3.1, -5.2],
      [3.6, -3.2],
    ],
  },
  {
    id: 'pitt-crossing',
    kind: 'street',
    points: [
      [5.1, -2],
      [5.4, 0.4],
      [6, 2.6],
      [7, 4.3],
    ],
  },
  {
    id: 'coquitlam-north',
    kind: 'street',
    points: [
      [2.2, -4],
      [2.6, -6],
      [3.4, -8],
    ],
  },
  {
    id: 'delta-west',
    kind: 'street',
    points: [
      [-12.8, 2.6],
      [-15, 5],
      [-16.5, 7.2],
    ],
  },
  {
    id: 'langley-south',
    kind: 'street',
    points: [
      [9.4, 5.6],
      [9.9, 8.6],
      [10.4, 11],
    ],
  },
  {
    id: 'maple-ridge-spur',
    kind: 'street',
    points: [
      [12.5, -2.7],
      [12.8, -5],
      [13.4, -7],
    ],
  },
]

export const BRIDGES: BridgeSpan[] = [
  // Burrard Inlet — the north-shore link crosses open water here.
  { id: 'burrard-inlet', from: [-8.6, -5.2], to: [-8.75, -8], width: 1.9 },
  // Pitt River — the pitt-crossing connector spans the gap.
  { id: 'pitt-river', from: [5.3, -0.4], to: [5.7, 2], width: 1.2 },
]
