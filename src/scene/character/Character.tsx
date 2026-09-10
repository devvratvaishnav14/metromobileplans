import { useEffect, useMemo, useRef, type RefObject } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import type { CharacterState } from './characterConfig'
import { createBoy } from './boyModel'
import { createIdleClip, createWalkClip } from './boyAnimations'

const FADE = 0.32 // seconds to cross-fade between states
/** Ground speed the (longer-stride) walk clip covers at timeScale 1. */
const NATURAL_WALK_SPEED = 1.4

/** One-shot phone buzz shortly after load — a notification arriving. */
const BUZZ_DELAY_MS = 1200
const BUZZ_DURATION = 0.5 // seconds

function prefersReducedMotion() {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

interface Actions {
  idle: THREE.AnimationAction
  walk: THREE.AnimationAction
}

/**
 * The boy, rendered. Builds the jointed rig once, wires an AnimationMixer with
 * the idle + walk clips, and cross-fades between them whenever `state` changes.
 *
 * The clips animate the *body* only (they never touch the model root), so the
 * controller is free to translate the wrapper group through the world. When
 * `moveSpeed` is supplied the walk cycle is time-scaled to roughly match the
 * actual ground speed, so the feet don't skate.
 */
export function Character({
  state,
  moveSpeed,
}: {
  state: CharacterState
  moveSpeed?: RefObject<number>
}) {
  const model = useMemo(() => createBoy(), [])
  const mixerRef = useRef<THREE.AnimationMixer | null>(null)
  const actionsRef = useRef<Actions | null>(null)
  const currentRef = useRef<CharacterState>('idle')

  // Phone buzz: the phone group hangs off the right hand and is never keyframed,
  // so we can nudge its local transform directly and restore it afterwards.
  const phoneRef = useRef<THREE.Object3D | null>(null)
  const phoneRestRef = useRef<{ rotZ: number; posX: number } | null>(null)
  const buzzTimeRef = useRef(-1) // seconds elapsed into the buzz, or -1 when idle

  useEffect(() => {
    const phone = model.root.getObjectByName('phone') ?? null
    phoneRef.current = phone
    if (phone) {
      phoneRestRef.current = { rotZ: phone.rotation.z, posX: phone.position.x }
    }
    if (prefersReducedMotion()) return

    const t = window.setTimeout(() => {
      buzzTimeRef.current = 0
    }, BUZZ_DELAY_MS)
    return () => window.clearTimeout(t)
  }, [model])

  useEffect(() => {
    const mixer = new THREE.AnimationMixer(model.root)
    const idle = mixer.clipAction(createIdleClip())
    const walk = mixer.clipAction(createWalkClip())
    idle.play()
    walk.play()
    walk.setEffectiveWeight(0)

    mixerRef.current = mixer
    actionsRef.current = { idle, walk }
    currentRef.current = 'idle'

    return () => {
      mixer.stopAllAction()
      mixer.uncacheRoot(model.root)
      mixerRef.current = null
      actionsRef.current = null
      model.dispose()
    }
  }, [model])

  useEffect(() => {
    const actions = actionsRef.current
    if (!actions || state === currentRef.current) return

    const to: THREE.AnimationAction = actions[state]
    const from: THREE.AnimationAction = actions[currentRef.current]
    to.reset()
    to.setEffectiveWeight(1)
    to.setEffectiveTimeScale(1)
    to.play()
    from.crossFadeTo(to, FADE, false)
    currentRef.current = state
  }, [state])

  useFrame((_, delta) => {
    const mixer = mixerRef.current
    const actions = actionsRef.current
    if (!mixer || !actions) return

    if (moveSpeed && currentRef.current === 'walk') {
      const ts = THREE.MathUtils.clamp(
        (moveSpeed.current ?? 0) / NATURAL_WALK_SPEED,
        0.85,
        2.6,
      )
      actions.walk.timeScale = ts
    }

    mixer.update(delta)

    // subtle notification buzz on the phone only
    const phone = phoneRef.current
    const rest = phoneRestRef.current
    if (phone && rest && buzzTimeRef.current >= 0) {
      buzzTimeRef.current += delta
      const tt = buzzTimeRef.current
      if (tt >= BUZZ_DURATION) {
        phone.rotation.z = rest.rotZ
        phone.position.x = rest.posX
        buzzTimeRef.current = -1
      } else {
        const decay = 1 - tt / BUZZ_DURATION
        phone.rotation.z = rest.rotZ + Math.sin(tt * 92) * 0.05 * decay
        phone.position.x = rest.posX + Math.sin(tt * 78) * 0.004 * decay
      }
    }
  })

  return <primitive object={model.root} />
}
