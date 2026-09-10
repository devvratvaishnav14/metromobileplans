/**
 * Shared configuration for the protagonist — a calm lofi-style boy. Holds the
 * rig layout, palette, scale and test placement. `boyModel.ts` builds geometry
 * from `RIG`; `boyAnimations.ts` builds clips against the same joint names and
 * rest positions, so the two stay in lock-step.
 */

export type CharacterState = 'idle' | 'walk'

/** Final height in world units. He is a small figure in the toy town —
 *  shorter than the trees and mid-rise buildings, clearly not a giant, but
 *  big enough to read as a character on the map. */
export const CHARACTER_HEIGHT = 1.05

export const PALETTE = {
  skin: '#f1c9a5',
  skinShade: '#e3b088',
  cheek: '#e59a86',
  hair: '#211c1c', // near-black, cool
  hairHi: '#5f2f39', // faint warm strands (ref: burgundy tint)
  brow: '#2a2320',
  eye: '#20242c',
  mouth: '#bd6a5e',
  top: '#5c7fc0', // periwinkle-blue hoodie / sweater
  topShade: '#4a6aa8',
  topCuff: '#42609a',
  hood: '#4f6fae',
  pants: '#39405a', // dark denim / navy
  shoe: '#2c2926',
  shoeSole: '#d8d2c6',
  headphone: '#e0e5eb', // light grey cans (ref 1)
  headphoneShade: '#b7bec8',
  headphonePad: '#2f333b',
  headphoneGlow: '#4fd6e6', // subtle cyan accent ring (refs 2 & 4)
  phone: '#1f2329',
  phoneScreen: '#bfe2ff',
} as const

/**
 * Joint layout — local position of each joint relative to its parent, in
 * model units (the whole rig is scaled to CHARACTER_HEIGHT at build time).
 * Parent chain:
 *   root > hips > spine > chest > (neck > head) | (shoulder* > upperArm* >
 *   lowerArm* > hand*) ; hips > thigh* > shin* > foot*
 *
 * ~5 heads tall — a young, slightly stylised boy (chunky limbs, larger head,
 * short legs), not an adult.
 */
export const RIG = {
  hips: [0, 0.62, 0],
  spine: [0, 0.1, 0],
  chest: [0, 0.2, 0],

  neck: [0, 0.11, 0],
  head: [0, 0.09, 0],

  shoulderL: [0.13, 0.04, 0],
  shoulderR: [-0.13, 0.04, 0],
  upperArmL: [0.03, -0.02, 0],
  upperArmR: [-0.03, -0.02, 0],
  lowerArmL: [0, -0.17, 0],
  lowerArmR: [0, -0.17, 0],
  handL: [0, -0.16, 0],
  handR: [0, -0.16, 0],

  thighL: [0.078, -0.02, 0],
  thighR: [-0.078, -0.02, 0],
  shinL: [0, -0.26, 0],
  shinR: [0, -0.26, 0],
  footL: [0, -0.24, 0],
  footR: [0, -0.24, 0],
} as const

export type JointName = keyof typeof RIG

/** Segment lengths derived from the rig, used by the geometry builder. */
export const SEG = {
  upperArm: 0.18,
  lowerArm: 0.16,
  thigh: 0.26,
  shin: 0.24,
} as const
