import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react'
import './cinematic.css'

interface Props {
  /** 'in' while the map camera dives in; 'out' once the analysis view is mounting. */
  stage: 'in' | 'out'
  /** Screen-space origin (0-100 %) for the wash, snapshotted on mount. */
  focusRef: RefObject<{ x: number; y: number }>
}

/**
 * The full-screen wash that bridges the miniature map and the plan-analysis
 * interface: it blooms out from the selected municipality to cover the swap,
 * then clears to reveal the analysis view. Decorative only.
 */
export function CinematicTransition({ stage, focusRef }: Props) {
  const el = useRef<HTMLDivElement>(null)
  const [gone, setGone] = useState(false)

  // snapshot the municipality's screen position once, straight onto the element
  useLayoutEffect(() => {
    const f = focusRef.current
    if (el.current && f) {
      el.current.style.setProperty('--fx', `${f.x}%`)
      el.current.style.setProperty('--fy', `${f.y}%`)
    }
  }, [focusRef])

  useEffect(() => {
    if (stage !== 'out') return
    const t = window.setTimeout(() => setGone(true), 720)
    return () => window.clearTimeout(t)
  }, [stage])

  if (gone) return null

  return (
    <div ref={el} className={`cine cine--${stage}`} aria-hidden="true">
      <div className="cine__wash" />
      <div className="cine__streaks" />
    </div>
  )
}
