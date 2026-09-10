import * as THREE from 'three'
import {
  CHARACTER_HEIGHT,
  PALETTE,
  RIG,
  SEG,
  type JointName,
} from './characterConfig'

/**
 * Builds the stylised lofi boy as a jointed hierarchy of shaped meshes — a real
 * skeletal rig (named joint groups driven by the animation clips), not a
 * skinned mesh.
 *
 * Design direction (from the lofi reference art): dark tousled hair with a
 * faint warm strand or two, big light-grey over-ear headphones as the key
 * identifying accessory (with a subtle cyan accent ring), a cosy periwinkle
 * hoodie with the hood down, dark denim, low-top sneakers, a phone in his
 * right hand. Calm, soft, youthful — no scarf, no bag.
 *
 * Returns the root (scaled to CHARACTER_HEIGHT, feet at local y = 0) plus the
 * joint map for the animation system.
 */

export interface BoyModel {
  root: THREE.Group
  joints: Record<JointName, THREE.Object3D>
  dispose: () => void
}

type V3 = [number, number, number]

interface MeshOpts {
  pos?: V3
  rot?: V3
  scale?: number | V3
  rough?: number
  flat?: boolean
  emissive?: string
  emissiveIntensity?: number
}

export function createBoy(): BoyModel {
  const disposables: { dispose: () => void }[] = []

  const mat = (color: string, o: MeshOpts = {}) => {
    const m = new THREE.MeshStandardMaterial({
      color,
      roughness: o.rough ?? 0.85,
      metalness: 0,
      flatShading: o.flat ?? false,
      emissive: o.emissive ? new THREE.Color(o.emissive) : new THREE.Color(0x000000),
      emissiveIntensity: o.emissiveIntensity ?? 1,
    })
    disposables.push(m)
    return m
  }

  const mesh = (geo: THREE.BufferGeometry, color: string, o: MeshOpts = {}) => {
    disposables.push(geo)
    const m = new THREE.Mesh(geo, mat(color, o))
    m.castShadow = true
    m.receiveShadow = true
    m.raycast = () => {}
    if (o.pos) m.position.set(...o.pos)
    if (o.rot) m.rotation.set(...o.rot)
    if (o.scale !== undefined) {
      const s = o.scale
      if (Array.isArray(s)) m.scale.set(...s)
      else m.scale.setScalar(s)
    }
    return m
  }

  const sphere = (r: number, color: string, o?: MeshOpts) =>
    mesh(new THREE.SphereGeometry(r, 18, 14), color, o)

  /** Tapered limb: top at y = 0, tapering to -len. */
  const limb = (topR: number, botR: number, len: number, color: string, o: MeshOpts = {}) => {
    const g = new THREE.CylinderGeometry(topR, botR, len, 14, 1)
    g.translate(0, -len / 2, 0)
    return mesh(g, color, o)
  }

  // ---------------------------------------------------------------- skeleton --
  const joints = {} as Record<JointName, THREE.Object3D>
  const J = (name: JointName, parent: THREE.Object3D) => {
    const g = new THREE.Group()
    g.name = name
    g.position.set(...(RIG[name] as unknown as V3))
    parent.add(g)
    joints[name] = g
    return g
  }

  const root = new THREE.Group()
  root.name = 'boyRoot'

  const hips = J('hips', root)
  const spine = J('spine', hips)
  const chest = J('chest', spine)
  const neck = J('neck', chest)
  const head = J('head', neck)
  const shoulderL = J('shoulderL', chest)
  const shoulderR = J('shoulderR', chest)
  const upperArmL = J('upperArmL', shoulderL)
  const upperArmR = J('upperArmR', shoulderR)
  const lowerArmL = J('lowerArmL', upperArmL)
  const lowerArmR = J('lowerArmR', upperArmR)
  const handL = J('handL', lowerArmL)
  const handR = J('handR', lowerArmR)
  const thighL = J('thighL', hips)
  const thighR = J('thighR', hips)
  const shinL = J('shinL', thighL)
  const shinR = J('shinR', thighR)
  const footL = J('footL', shinL)
  const footR = J('footR', shinR)

  // ---------------------------------------------------------------- geometry --

  // hips / pelvis — a short block bridging torso to legs, fully hidden by the
  // hoodie hem
  hips.add(mesh(new THREE.CylinderGeometry(0.09, 0.084, 0.16, 18), PALETTE.pants, { pos: [0, -0.04, 0], rough: 0.9 }))

  // torso — an oversized cosy hoodie that falls to the hip / upper thigh (a
  // lofi silhouette that also hides the hip/leg junction). Soft, boxy, hangs
  // straight — no flare at the hem.
  const torsoProfile = [
    [0.04, -0.36],
    [0.103, -0.34], // hem
    [0.103, -0.24],
    [0.1, -0.12],
    [0.101, 0.0],
    [0.114, 0.1], // chest
    [0.112, 0.15],
    [0.08, 0.2],
    [0.056, 0.235],
  ].map(([x, y]) => new THREE.Vector2(x, y))
  chest.add(mesh(new THREE.LatheGeometry(torsoProfile, 24), PALETTE.top, { rough: 0.92 }))
  // ribbed hem band — same width as the body, hangs straight
  chest.add(mesh(new THREE.CylinderGeometry(0.104, 0.101, 0.04, 20), PALETTE.topShade, { pos: [0, -0.35, 0], rough: 0.92 }))
  // crew collar
  chest.add(
    mesh(new THREE.TorusGeometry(0.05, 0.016, 10, 22), PALETTE.topShade, {
      pos: [0, 0.2, 0.006],
      rot: [Math.PI / 2 - 0.2, 0, 0],
      scale: [1.35, 1, 1.05],
      rough: 0.92,
    }),
  )
  // hood, down — a soft folded roll resting across the upper back
  chest.add(sphere(0.088, PALETTE.hood, { pos: [0, 0.135, -0.07], scale: [1.25, 0.7, 0.66], rough: 0.95 }))
  chest.add(sphere(0.06, PALETTE.top, { pos: [0, 0.06, -0.082], scale: [1.35, 0.85, 0.5], rough: 0.95 }))
  // drawstrings down the chest
  chest.add(mesh(new THREE.CylinderGeometry(0.006, 0.006, 0.12, 8), PALETTE.topShade, { pos: [0.028, 0.05, 0.098], rot: [0.1, 0, 0.03] }))
  chest.add(mesh(new THREE.CylinderGeometry(0.006, 0.006, 0.1, 8), PALETTE.topShade, { pos: [-0.028, 0.06, 0.098], rot: [0.1, 0, -0.03] }))
  chest.add(sphere(0.01, PALETTE.headphone, { pos: [0.028, -0.015, 0.1] }))
  chest.add(sphere(0.01, PALETTE.headphone, { pos: [-0.028, -0.005, 0.1] }))
  // kangaroo-pocket seam, just a hint
  chest.add(mesh(new THREE.BoxGeometry(0.14, 0.07, 0.018), PALETTE.topShade, { pos: [0, -0.17, 0.088], rot: [0.05, 0, 0], rough: 0.92 }))

  // neck — a touch shorter/sturdier
  neck.add(limb(0.05, 0.054, 0.1, PALETTE.skin, { pos: [0, 0.05, 0] }))

  // head
  const headR = 0.135
  head.add(sphere(headR, PALETTE.skin, { pos: [0, 0.012, 0], scale: [1, 1.04, 0.99] }))
  // jaw / chin — a slightly squarer boyish jaw
  head.add(sphere(headR * 0.78, PALETTE.skin, { pos: [0, -0.062, 0.012], scale: [0.92, 0.82, 0.9] }))
  head.add(sphere(0.019, PALETTE.skin, { pos: [headR - 0.014, -0.006, 0] }))
  head.add(sphere(0.019, PALETTE.skin, { pos: [-(headR - 0.014), -0.006, 0] }))

  // face — calm, understated
  const fz = 0.118
  head.add(sphere(1, PALETTE.eye, { pos: [0.05, 0.006, fz], scale: [0.023, 0.03, 0.02] }))
  head.add(sphere(1, PALETTE.eye, { pos: [-0.05, 0.006, fz], scale: [0.023, 0.03, 0.02] }))
  head.add(sphere(1, '#ffffff', { pos: [0.056, 0.017, fz + 0.012], scale: [0.007, 0.007, 0.005] }))
  head.add(sphere(1, '#ffffff', { pos: [-0.044, 0.017, fz + 0.012], scale: [0.007, 0.007, 0.005] }))
  head.add(mesh(new THREE.BoxGeometry(0.042, 0.009, 0.01), PALETTE.brow, { pos: [0.05, 0.04, fz - 0.004], rot: [0, 0, -0.06] }))
  head.add(mesh(new THREE.BoxGeometry(0.042, 0.009, 0.01), PALETTE.brow, { pos: [-0.05, 0.04, fz - 0.004], rot: [0, 0, 0.06] }))
  // nose + mouth
  head.add(sphere(0.014, PALETTE.skinShade, { pos: [0, -0.022, fz + 0.014] }))
  head.add(sphere(1, PALETTE.mouth, { pos: [0, -0.055, fz + 0.002], scale: [0.019, 0.006, 0.008] }))
  head.add(sphere(1, PALETTE.cheek, { pos: [0.078, -0.03, fz - 0.036], scale: [0.02, 0.014, 0.01] }))
  head.add(sphere(1, PALETTE.cheek, { pos: [-0.078, -0.03, fz - 0.036], scale: [0.02, 0.014, 0.01] }))

  // hair — dark, tousled, a little messy. A skullcap + short back, then several
  // angled tufts poking up and forward. Kept as chunky shapes so it reads at
  // the miniature-world camera distance.
  const hair = (o: MeshOpts) => head.add(sphere(1, PALETTE.hair, { rough: 0.95, ...o }))
  head.add(
    mesh(new THREE.SphereGeometry(headR + 0.014, 24, 16, 0, Math.PI * 2, 0, Math.PI * 0.52), PALETTE.hair, {
      pos: [0, 0.014, -0.004],
      scale: [1.04, 1.05, 1.06],
      rough: 0.95,
    }),
  )
  // short back + sides, cropped around the nape (not a bob)
  head.add(
    mesh(
      new THREE.SphereGeometry(headR + 0.016, 24, 18, Math.PI / 2 + 0.7, Math.PI * 2 - 1.4, Math.PI * 0.3, Math.PI * 0.46),
      PALETTE.hair,
      { pos: [0, 0.02, -0.006], scale: [1.03, 0.86, 1.05], rough: 0.95 },
    ),
  )
  // tousled fringe — asymmetric spikes over the brow
  hair({ pos: [0.0, 0.086, 0.07], scale: [0.11, 0.055, 0.06], rot: [0.4, 0.1, 0.05] })
  hair({ pos: [0.062, 0.09, 0.056], scale: [0.05, 0.06, 0.05], rot: [0.5, 0, 0.35] })
  hair({ pos: [-0.05, 0.094, 0.058], scale: [0.045, 0.05, 0.045], rot: [0.45, 0, -0.4] })
  hair({ pos: [0.11, 0.062, 0.03], scale: [0.035, 0.06, 0.04], rot: [0.2, 0, 0.6] })
  // messy tufts standing up at the crown / back
  hair({ pos: [0.02, 0.14, 0.01], scale: [0.05, 0.06, 0.05], rot: [-0.1, 0.2, 0.15] })
  hair({ pos: [-0.03, 0.135, -0.03], scale: [0.045, 0.055, 0.05], rot: [-0.25, -0.2, -0.1] })
  hair({ pos: [0.06, 0.12, -0.04], scale: [0.04, 0.05, 0.045], rot: [-0.3, 0.1, 0.3] })
  // faint warm strands (kept subtle — a couple of thin slivers)
  head.add(sphere(1, PALETTE.hairHi, { pos: [0.04, 0.108, 0.052], scale: [0.012, 0.05, 0.03], rot: [0.4, 0, 0.2], rough: 0.9 }))
  head.add(sphere(1, PALETTE.hairHi, { pos: [-0.02, 0.128, 0.02], scale: [0.01, 0.045, 0.03], rot: [-0.1, 0, -0.1], rough: 0.9 }))
  // sideburn hints
  hair({ pos: [0.104, -0.03, 0.03], scale: [0.02, 0.05, 0.028] })
  hair({ pos: [-0.104, -0.03, 0.03], scale: [0.02, 0.05, 0.028] })

  // headphones — the key accessory. Big light-grey over-ear cans on a band
  // over the crown, a dark pad facing the ear, a faint cyan accent ring.
  const hp = new THREE.Group()
  hp.name = 'headphones'
  head.add(hp)
  // band arcing over the top, ear to ear
  hp.add(
    mesh(new THREE.TorusGeometry(0.156, 0.02, 12, 28, Math.PI * 1.04), PALETTE.headphone, {
      pos: [0, -0.006, -0.006],
      rot: [0.06, 0, 0],
      scale: [1, 1.06, 1],
      rough: 0.55,
    }),
  )
  hp.add(
    mesh(new THREE.TorusGeometry(0.156, 0.022, 10, 24, Math.PI * 0.5), PALETTE.headphoneShade, {
      pos: [0, -0.006, -0.028],
      rot: [0.5, 0, 0],
      rough: 0.55,
    }),
  )
  // ear cups
  for (const s of [1, -1] as const) {
    const cup = new THREE.Group()
    cup.position.set(s * (headR + 0.03), -0.01, 0.006)
    hp.add(cup)
    // outer shell
    cup.add(
      mesh(new THREE.CylinderGeometry(0.056, 0.056, 0.03, 22), PALETTE.headphone, {
        rot: [0, 0, Math.PI / 2],
        scale: [1, 1, 1.06],
        rough: 0.5,
      }),
    )
    // soft ear pad, facing in
    cup.add(
      mesh(new THREE.CylinderGeometry(0.05, 0.052, 0.024, 22), PALETTE.headphonePad, {
        pos: [s * -0.02, 0, 0],
        rot: [0, 0, Math.PI / 2],
        rough: 0.9,
      }),
    )
    // faint cyan accent ring on the outer face
    cup.add(
      mesh(new THREE.TorusGeometry(0.038, 0.005, 8, 24), PALETTE.headphoneGlow, {
        pos: [s * 0.018, 0, 0],
        rot: [0, Math.PI / 2, 0],
        emissive: PALETTE.headphoneGlow,
        emissiveIntensity: 0.6,
        rough: 0.4,
      }),
    )
    // yoke connecting band to cup
    cup.add(
      mesh(new THREE.BoxGeometry(0.014, 0.05, 0.03), PALETTE.headphoneShade, {
        pos: [s * 0.02, 0.04, 0],
        rot: [0, 0, s * -0.2],
        rough: 0.5,
      }),
    )
  }

  // arms — hoodie sleeves, a little loose, ribbed cuff, bare hands
  shoulderL.add(sphere(0.047, PALETTE.top, { scale: [1, 0.88, 1] }))
  shoulderR.add(sphere(0.047, PALETTE.top, { scale: [1, 0.88, 1] }))
  upperArmL.add(limb(0.046, 0.042, SEG.upperArm + 0.03, PALETTE.top))
  upperArmR.add(limb(0.046, 0.042, SEG.upperArm + 0.03, PALETTE.top))
  lowerArmL.add(limb(0.042, 0.038, SEG.lowerArm - 0.02, PALETTE.top, { pos: [0, 0.005, 0] }))
  lowerArmR.add(limb(0.042, 0.038, SEG.lowerArm - 0.02, PALETTE.top, { pos: [0, 0.005, 0] }))
  lowerArmL.add(mesh(new THREE.CylinderGeometry(0.04, 0.038, 0.026, 14), PALETTE.topCuff, { pos: [0, -0.13, 0] }))
  lowerArmR.add(mesh(new THREE.CylinderGeometry(0.04, 0.038, 0.026, 14), PALETTE.topCuff, { pos: [0, -0.13, 0] }))
  lowerArmL.add(limb(0.031, 0.029, 0.05, PALETTE.skin, { pos: [0, -0.14, 0] }))
  lowerArmR.add(limb(0.031, 0.029, 0.05, PALETTE.skin, { pos: [0, -0.14, 0] }))
  handL.add(sphere(0.04, PALETTE.skin, { pos: [0, -0.02, 0], scale: [1, 1.05, 0.78] }))
  handR.add(sphere(0.04, PALETTE.skin, { pos: [0, -0.02, 0], scale: [1, 1.05, 0.78] }))

  // phone, in the right hand — kept small, but sized/angled/lit so it still
  // reads as a phone from the normal map camera distance. Same name +
  // transform as before so the notification-buzz code keeps working.
  const phone = new THREE.Group()
  phone.name = 'phone'
  phone.add(mesh(new THREE.BoxGeometry(0.0712, 0.1266, 0.0138), PALETTE.phone, { flat: true, rough: 0.5 }))
  phone.add(
    mesh(new THREE.BoxGeometry(0.0585, 0.1064, 0.006), PALETTE.phoneScreen, {
      pos: [0, 0.004, 0.0093],
      rough: 0.3,
      emissive: PALETTE.phoneScreen,
      emissiveIntensity: 0.4,
    }),
  )
  phone.position.set(0, -0.05, 0.033)
  phone.rotation.set(-0.82, 0, 0)
  handR.add(phone)

  // legs — dark denim, chunky and short (young + stylised)
  thighL.add(limb(0.076, 0.06, SEG.thigh + 0.05, PALETTE.pants, { pos: [0, 0.05, 0] }))
  thighR.add(limb(0.076, 0.06, SEG.thigh + 0.05, PALETTE.pants, { pos: [0, 0.05, 0] }))
  shinL.add(sphere(0.056, PALETTE.pants, { pos: [0, 0.015, 0] }))
  shinR.add(sphere(0.056, PALETTE.pants, { pos: [0, 0.015, 0] }))
  shinL.add(limb(0.053, 0.04, SEG.shin + 0.03, PALETTE.pants))
  shinR.add(limb(0.053, 0.04, SEG.shin + 0.03, PALETTE.pants))
  // low-top sneakers — a dark upper with a lighter sole slab
  const shoe = (j: THREE.Object3D) => {
    j.add(mesh(new THREE.BoxGeometry(0.062, 0.044, 0.12), PALETTE.shoe, { pos: [0, -0.004, 0.036], flat: true }))
    j.add(mesh(new THREE.BoxGeometry(0.066, 0.02, 0.13), PALETTE.shoeSole, { pos: [0, -0.026, 0.038], flat: true }))
    j.add(sphere(1, PALETTE.shoe, { pos: [0, 0.006, -0.012], scale: [0.032, 0.03, 0.03], flat: true }))
  }
  shoe(footL)
  shoe(footR)

  // ------------------------------------------------- rest pose + normalise --
  shoulderL.rotation.z = -0.1
  shoulderR.rotation.z = 0.1
  upperArmL.rotation.x = 0.08
  upperArmR.rotation.x = 0.08
  lowerArmL.rotation.x = 0.16
  lowerArmR.rotation.x = 0.16

  root.updateMatrixWorld(true)
  const box = new THREE.Box3().setFromObject(root)
  const scale = CHARACTER_HEIGHT / (box.max.y - box.min.y)
  root.scale.setScalar(scale)
  root.position.y = -box.min.y * scale

  root.traverse((o) => {
    o.raycast = () => {}
  })

  return {
    root,
    joints,
    dispose: () => disposables.forEach((d) => d.dispose()),
  }
}
