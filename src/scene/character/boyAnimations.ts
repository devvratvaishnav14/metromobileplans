import * as THREE from 'three'
import { RIG } from './characterConfig'

/**
 * Hand-authored animation clips for the jointed rig. Both clips drive the same
 * joint set (quaternions + the hip position track) so the AnimationMixer can
 * cross-fade cleanly between them. Times are seconds; every clip loops.
 */

const _e = new THREE.Euler()
const _q = new THREE.Quaternion()

function q(x = 0, y = 0, z = 0): number[] {
  _e.set(x, y, z)
  _q.setFromEuler(_e)
  return [_q.x, _q.y, _q.z, _q.w]
}

function qt(joint: string, times: number[], eulers: [number, number, number][]) {
  const values: number[] = []
  for (const e of eulers) values.push(...q(e[0], e[1], e[2]))
  return new THREE.QuaternionKeyframeTrack(`${joint}.quaternion`, times, values)
}

function vt(joint: string, times: number[], vecs: [number, number, number][]) {
  return new THREE.VectorKeyframeTrack(`${joint}.position`, times, vecs.flat())
}

const hipBase = RIG.hips as unknown as [number, number, number]

// --------------------------------------------------------------------- IDLE --
// Standing still, phone held up in both hands, head tilted down toward it,
// gentle breathing + a slow weight shift. Loop length 4 s.
export function createIdleClip(): THREE.AnimationClip {
  const T = [0, 1, 2, 3, 4]

  const tracks = [
    vt('hips', T, [
      [hipBase[0], hipBase[1], hipBase[2]],
      [hipBase[0] + 0.006, hipBase[1] + 0.004, hipBase[2]],
      [hipBase[0], hipBase[1] - 0.003, hipBase[2]],
      [hipBase[0] - 0.006, hipBase[1] + 0.004, hipBase[2]],
      [hipBase[0], hipBase[1], hipBase[2]],
    ]),
    qt('hips', T, [
      [0, 0, 0.02],
      [0, 0.01, 0.03],
      [0, 0, 0.0],
      [0, -0.01, -0.03],
      [0, 0, 0.02],
    ]),
    qt('spine', T, [
      [0.02, 0, -0.01],
      [0.035, 0.01, -0.02],
      [0.02, 0, 0],
      [0.035, -0.01, 0.02],
      [0.02, 0, -0.01],
    ]),
    qt('chest', T, [
      [0.01, 0, 0],
      [0.028, 0, 0],
      [0.01, 0, 0],
      [0.028, 0, 0],
      [0.01, 0, 0],
    ]),
    qt('neck', T, [
      [0.13, 0.02, 0],
      [0.14, -0.01, 0],
      [0.12, 0.03, 0],
      [0.14, 0.0, 0],
      [0.13, 0.02, 0],
    ]),
    qt('head', T, [
      [0.36, 0.03, 0],
      [0.39, -0.02, 0.01],
      [0.34, 0.04, 0],
      [0.39, 0.0, -0.01],
      [0.36, 0.03, 0],
    ]),
    // both hands up holding the phone in front, elbows bent ~90 deg
    qt('shoulderL', T, [[0, 0, -0.06], [0, 0, -0.05], [0, 0, -0.07], [0, 0, -0.05], [0, 0, -0.06]]),
    qt('shoulderR', T, [[0, 0, 0.06], [0, 0, 0.05], [0, 0, 0.07], [0, 0, 0.05], [0, 0, 0.06]]),
    qt('upperArmL', T, [
      [-0.42, 0, -0.16],
      [-0.41, 0, -0.16],
      [-0.44, 0, -0.16],
      [-0.41, 0, -0.16],
      [-0.42, 0, -0.16],
    ]),
    qt('upperArmR', T, [
      [-0.42, 0, 0.16],
      [-0.44, 0, 0.16],
      [-0.41, 0, 0.16],
      [-0.44, 0, 0.16],
      [-0.42, 0, 0.16],
    ]),
    qt('lowerArmL', T, [
      [-1.55, 0, -0.12],
      [-1.56, 0, -0.12],
      [-1.54, 0, -0.12],
      [-1.56, 0, -0.12],
      [-1.55, 0, -0.12],
    ]),
    qt('lowerArmR', T, [
      [-1.55, 0, 0.12],
      [-1.54, 0, 0.12],
      [-1.56, 0, 0.12],
      [-1.54, 0, 0.12],
      [-1.55, 0, 0.12],
    ]),
    qt('handL', T, [[0.2, 0, -0.1], [0.2, 0, -0.1], [0.2, 0, -0.1], [0.2, 0, -0.1], [0.2, 0, -0.1]]),
    qt('handR', T, [[0.2, 0, 0.1], [0.2, 0, 0.1], [0.2, 0, 0.1], [0.2, 0, 0.1], [0.2, 0, 0.1]]),
    // relaxed stance — weight on one leg, the other knee soft
    qt('thighL', T, [[-0.05, 0, 0.06], [-0.06, 0, 0.06], [-0.04, 0, 0.06], [-0.06, 0, 0.06], [-0.05, 0, 0.06]]),
    qt('thighR', T, [[0.06, 0, -0.05], [0.05, 0, -0.05], [0.07, 0, -0.05], [0.05, 0, -0.05], [0.06, 0, -0.05]]),
    qt('shinL', T, [[0.14, 0, 0], [0.13, 0, 0], [0.15, 0, 0], [0.13, 0, 0], [0.14, 0, 0]]),
    qt('shinR', T, [[0.08, 0, 0], [0.09, 0, 0], [0.07, 0, 0], [0.09, 0, 0], [0.08, 0, 0]]),
    qt('footL', T, [[-0.06, 0, 0], [-0.06, 0, 0], [-0.06, 0, 0], [-0.06, 0, 0], [-0.06, 0, 0]]),
    qt('footR', T, [[-0.02, 0, 0], [-0.02, 0, 0], [-0.02, 0, 0], [-0.02, 0, 0], [-0.02, 0, 0]]),
  ]

  return new THREE.AnimationClip('idle', 4, tracks)
}

// --------------------------------------------------------------------- WALK --
// Two-step cycle, head up and forward, arms swinging (phone just rides along in
// the right hand). Loop length 0.9 s.
export function createWalkClip(): THREE.AnimationClip {
  const T = [0, 0.225, 0.45, 0.675, 0.9]

  const tracks = [
    vt('hips', T, [
      [hipBase[0] + 0.015, hipBase[1] - 0.016, hipBase[2]],
      [hipBase[0], hipBase[1] + 0.006, hipBase[2]],
      [hipBase[0] - 0.015, hipBase[1] - 0.016, hipBase[2]],
      [hipBase[0], hipBase[1] + 0.006, hipBase[2]],
      [hipBase[0] + 0.015, hipBase[1] - 0.016, hipBase[2]],
    ]),
    qt('hips', T, [
      [0, 0.13, -0.05],
      [0, 0, 0.03],
      [0, -0.13, 0.05],
      [0, 0, -0.03],
      [0, 0.13, -0.05],
    ]),
    qt('spine', T, [
      [0.06, -0.09, 0.03],
      [0.06, 0, 0],
      [0.06, 0.09, -0.03],
      [0.06, 0, 0],
      [0.06, -0.09, 0.03],
    ]),
    qt('chest', T, [
      [0.03, -0.06, 0.02],
      [0.06, 0, 0],
      [0.03, 0.06, -0.02],
      [0.06, 0, 0],
      [0.03, -0.06, 0.02],
    ]),
    qt('neck', T, [[0.04, 0.03, 0], [0.05, 0, 0], [0.04, -0.03, 0], [0.05, 0, 0], [0.04, 0.03, 0]]),
    qt('head', T, [
      [0.08, -0.04, 0.01],
      [0.05, 0, 0],
      [0.08, 0.04, -0.01],
      [0.05, 0, 0],
      [0.08, -0.04, 0.01],
    ]),
    // arm counter-swing
    qt('shoulderL', T, [[0, 0, -0.12], [0, 0, -0.12], [0, 0, -0.12], [0, 0, -0.12], [0, 0, -0.12]]),
    qt('shoulderR', T, [[0, 0, 0.12], [0, 0, 0.12], [0, 0, 0.12], [0, 0, 0.12], [0, 0, 0.12]]),
    qt('upperArmL', T, [
      [0.52, 0.05, 0],
      [0.0, 0.05, 0],
      [-0.56, 0.05, 0],
      [-0.14, 0.05, 0],
      [0.52, 0.05, 0],
    ]),
    qt('upperArmR', T, [
      [-0.56, -0.05, 0],
      [-0.14, -0.05, 0],
      [0.52, -0.05, 0],
      [0.0, -0.05, 0],
      [-0.56, -0.05, 0],
    ]),
    qt('lowerArmL', T, [
      [-0.3, 0, 0],
      [-0.42, 0, 0],
      [-0.52, 0, 0],
      [-0.42, 0, 0],
      [-0.3, 0, 0],
    ]),
    qt('lowerArmR', T, [
      [-0.52, 0, 0],
      [-0.42, 0, 0],
      [-0.3, 0, 0],
      [-0.42, 0, 0],
      [-0.52, 0, 0],
    ]),
    qt('handL', T, [[0.05, 0, 0], [0.05, 0, 0], [0.05, 0, 0], [0.05, 0, 0], [0.05, 0, 0]]),
    qt('handR', T, [[0.1, 0, 0], [0.1, 0, 0], [0.1, 0, 0], [0.1, 0, 0], [0.1, 0, 0]]),
    // leg cycle — left leads. Wider swing so the shorter legs still cover a
    // natural stride.
    qt('thighL', T, [
      [-0.72, 0, 0.02],
      [0.0, 0, 0.02],
      [0.66, 0, 0.02],
      [0.14, 0, 0.02],
      [-0.72, 0, 0.02],
    ]),
    qt('thighR', T, [
      [0.66, 0, -0.02],
      [0.14, 0, -0.02],
      [-0.72, 0, -0.02],
      [0.0, 0, -0.02],
      [0.66, 0, -0.02],
    ]),
    qt('shinL', T, [[0.14, 0, 0], [0.06, 0, 0], [0.26, 0, 0], [1.16, 0, 0], [0.14, 0, 0]]),
    qt('shinR', T, [[0.26, 0, 0], [1.16, 0, 0], [0.14, 0, 0], [0.06, 0, 0], [0.26, 0, 0]]),
    qt('footL', T, [
      [-0.2, 0, 0],
      [0.02, 0, 0],
      [0.46, 0, 0],
      [-0.14, 0, 0],
      [-0.2, 0, 0],
    ]),
    qt('footR', T, [
      [0.46, 0, 0],
      [-0.14, 0, 0],
      [-0.2, 0, 0],
      [0.02, 0, 0],
      [0.46, 0, 0],
    ]),
  ]

  return new THREE.AnimationClip('walk', 0.9, tracks)
}
