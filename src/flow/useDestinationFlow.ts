import { useCallback, useEffect, useRef, useState } from 'react'
import { DESTINATIONS } from '../scene/navigation/destinations'
import { isSupportedMunicipality } from '../data/coverage'

/**
 * Where the user is in the "pick a municipality" journey:
 *
 *   browsing     — free to hover/click the map (also the initial state)
 *   traveling    — a municipality is chosen; the character is walking there
 *   confirming   — he has arrived and settled; the confirm notification is up
 *   confirmed    — the user said yes; his "[Place] it is." bubble is showing
 *   zooming      — the cinematic camera dive toward the selected municipality
 *   results      — the miniature map has swapped for the plan-analysis interface
 */
export type FlowPhase =
  | 'browsing'
  | 'traveling'
  | 'confirming'
  | 'confirmed'
  | 'zooming'
  | 'results'

/** ms to wait after arrival (route fade + idle settle) before asking to confirm. */
const CONFIRM_DELAY = 650
/** ms the "[Place] it is." bubble stays up before the cinematic begins. */
const BUBBLE_READ_MS = 1900
/** ms the cinematic dive runs (and the wash covers it) before the analysis view. */
const ZOOM_MS = 1150

export interface DestinationFlow {
  phase: FlowPhase
  /** Municipality the character is heading to / has reached, or null. */
  destinationId: string | null
  /** Display name for the confirm notification, or null when not confirming. */
  pendingName: string | null
  /** "[Place] it is." line for the speech bubble, or null. */
  spokenLine: string | null
  /** True while the map camera should be diving toward the municipality. */
  pushingIn: boolean
  /** True once the analysis interface has taken over. */
  showResults: boolean
  /** User clicked a municipality on the map. */
  selectMunicipality: (id: string) => void
  /** The character controller reports the character has arrived. */
  handleArrival: () => void
  /** User pressed "Yes" in the confirm notification. */
  confirm: () => void
  /** User pressed "Choose another area". */
  reject: () => void
  /** Leave the analysis interface and return to the map from the start. */
  restart: () => void
}

export function useDestinationFlow(): DestinationFlow {
  const [phase, setPhase] = useState<FlowPhase>('browsing')
  const [destinationId, setDestinationId] = useState<string | null>(null)
  const arrivalTimer = useRef<number | undefined>(undefined)
  const bubbleTimer = useRef<number | undefined>(undefined)

  const clearTimers = () => {
    window.clearTimeout(arrivalTimer.current)
    window.clearTimeout(bubbleTimer.current)
    arrivalTimer.current = undefined
    bubbleTimer.current = undefined
  }

  const selectMunicipality = useCallback((id: string) => {
    // Only Vancouver / Burnaby / Surrey are interactive on the map, so this is
    // only ever called for a supported municipality — the guard is defensive.
    if (!DESTINATIONS[id] || !isSupportedMunicipality(id)) return
    clearTimers()
    setDestinationId(id)
    setPhase('traveling')
  }, [])

  const handleArrival = useCallback(() => {
    clearTimers()
    arrivalTimer.current = window.setTimeout(() => {
      arrivalTimer.current = undefined
      setPhase((p) => (p === 'traveling' ? 'confirming' : p))
    }, CONFIRM_DELAY)
  }, [])

  const confirm = useCallback(() => {
    setPhase((p) => (p === 'confirming' ? 'confirmed' : p))
    window.clearTimeout(bubbleTimer.current)
    bubbleTimer.current = window.setTimeout(() => {
      bubbleTimer.current = undefined
      setPhase((p) => (p === 'confirmed' ? 'zooming' : p))
    }, BUBBLE_READ_MS)
  }, [])

  const reject = useCallback(() => {
    clearTimers()
    setDestinationId(null)
    setPhase('browsing')
  }, [])

  const restart = useCallback(() => {
    clearTimers()
    setDestinationId(null)
    setPhase('browsing')
  }, [])

  // Once the cinematic dive has run its course, hand over to the analysis view.
  useEffect(() => {
    if (phase !== 'zooming') return
    const t = window.setTimeout(() => setPhase('results'), ZOOM_MS)
    return () => window.clearTimeout(t)
  }, [phase])

  const name = destinationId ? (DESTINATIONS[destinationId]?.name ?? null) : null

  return {
    phase,
    destinationId,
    pendingName: phase === 'confirming' ? name : null,
    spokenLine:
      (phase === 'confirmed' || phase === 'zooming') && name
        ? `${name} it is.`
        : null,
    pushingIn: phase === 'zooming',
    showResults: phase === 'results',
    selectMunicipality,
    handleArrival,
    confirm,
    reject,
    restart,
  }
}
