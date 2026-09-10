import { useEffect, useState } from 'react'
import { useIsTouch } from './useIsTouch'

/** When each message slides in (ms after mount). */
const SHOW_AT = [2200, 3700, 5100]
/** Compressed schedule when the viewer prefers reduced motion. */
const SHOW_AT_REDUCED = [700, 1200, 1700]

/** One card's exit animation length (must match `onb-out` in overlay.css). */
const EXIT_DURATION = 820
/** Calm pause between one card finishing its exit and the next one starting. */
const EXIT_GAP = 340
/** Small buffer so the last animation fully settles before we unmount. */
const EXIT_TAIL = 80

function prefersReducedMotion() {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

interface Props {
  /** The opening intro is over once the boy starts a journey (or on manual close). */
  dismissed: boolean
  /** User tapped the subtle close control on the stack. */
  onClose: () => void
}

/**
 * The opening phone-style notification stack. Three messages arrive one after
 * another from the right edge. When dismissed they leave in a true sequence —
 * card 1 slides fully off, a short pause, then card 2, then card 3 — driven by
 * a JS timeline rather than shared CSS so only one card is ever in motion.
 * Shown once — never replayed.
 */
export function OnboardingNotifications({ dismissed, onClose }: Props) {
  const isTouch = useIsTouch()
  const [count, setCount] = useState(0)
  // How many cards have begun (or finished) their exit: 0 = none, 3 = all.
  const [exitStep, setExitStep] = useState(0)
  const [removed, setRemoved] = useState(false)

  useEffect(() => {
    const schedule = prefersReducedMotion() ? SHOW_AT_REDUCED : SHOW_AT
    const timers = schedule.map((delay, i) =>
      window.setTimeout(() => setCount(i + 1), delay),
    )
    return () => timers.forEach(clearTimeout)
  }, [])

  useEffect(() => {
    if (!dismissed) return
    const reduce = prefersReducedMotion()
    const step = reduce ? 120 : EXIT_DURATION + EXIT_GAP
    const tail = reduce ? 60 : EXIT_DURATION + EXIT_TAIL

    const timers = [
      window.setTimeout(() => setExitStep(1), 0),
      window.setTimeout(() => setExitStep(2), step),
      window.setTimeout(() => setExitStep(3), step * 2),
      window.setTimeout(() => setRemoved(true), step * 2 + tail),
    ]
    return () => timers.forEach(clearTimeout)
  }, [dismissed])

  if (removed || count === 0) return null

  const hint = isTouch
    ? 'Tap an area to choose'
    : 'Move around • Click an area to choose'

  const leaving = (index: number) =>
    exitStep >= index ? ' onb-card--leaving' : ''

  return (
    <div
      className={`onb-stack${dismissed ? ' onb-stack--exiting' : ''}`}
      role="status"
      aria-live="polite"
    >
      <span className="onb-ding" aria-hidden="true" />

      {count >= 1 && (
        <div className={`onb-card onb-card--lead${leaving(1)}`}>
          <div className="onb-card__head">
            <span className="onb-card__dot" aria-hidden="true" />
            <span className="onb-card__app">Metro Mobile Plans</span>
            <span className="onb-card__time">now</span>
            <button
              type="button"
              className="onb-card__close"
              onClick={onClose}
              aria-label="Dismiss intro"
            >
              &times;
            </button>
          </div>
          <p className="onb-card__title">Where will you be using your phone?</p>
        </div>
      )}

      {count >= 2 && (
        <div className={`onb-card${leaving(2)}`}>
          <p className="onb-card__body">
            Choose the area where you&rsquo;ll use your plan most. We&rsquo;ll
            compare the best options available there.
          </p>
        </div>
      )}

      {count >= 3 && (
        <div className={`onb-card onb-card--hint${leaving(3)}`}>
          <p className="onb-card__body">{hint}</p>
        </div>
      )}
    </div>
  )
}
