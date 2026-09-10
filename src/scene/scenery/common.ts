import * as THREE from 'three'

/**
 * Shared helpers for the decorative scenery layer.
 *
 * Scenery (roads, buildings, trees, mountains) is purely visual. It is NOT
 * the navigation system — a separate invisible walkable surface will be added
 * later for the character. Keep this layer free of collision / pathfinding and
 * independent of the municipality geographic data.
 */

/**
 * Every scenery mesh uses this as its `raycast` so it is invisible to pointer
 * picking. The municipality underneath must keep receiving hover events even
 * when the cursor is over a building, tree, road or mountain.
 */
export const ignoreRaycast: THREE.Object3D['raycast'] = () => {}

/** Top surface of the extruded municipality land — scenery rests on this. */
export const GROUND_Y = 0

/** Playful, slightly muted palette for the miniature world. */
export const PALETTE = {
  road: '#948b81',
  roadEdge: '#7d746a',
  roadMarking: '#f4eddc',
  building: {
    cream: '#e9dcbf',
    red: '#d76a52',
    orange: '#e79a5c',
    blue: '#6ba3cf',
    yellow: '#efc457',
    pastelGreen: '#a6d09c',
    pastelPurple: '#ac9ed2',
  },
  roof: {
    terracotta: '#c65b45',
    slate: '#5c6b7a',
    cream: '#e7dcc2',
    teal: '#4f9e97',
  },
  trunk: '#7a5238',
  foliage: ['#5fb257', '#4e9c45', '#79c96f', '#3f8d3c'],
  mountain: ['#3f6a37', '#4f7d40', '#5c8a49', '#6b9a55'],
  mountainRock: '#d0cabc',
} as const
