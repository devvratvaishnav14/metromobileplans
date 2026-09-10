import { useEffect, useState } from 'react'

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

/**
 * Counts a number up from 0 to `target` once, over `durationMs`, using
 * requestAnimationFrame — no dependency, no library. Honours
 * `prefers-reduced-motion` (returns `target` immediately, no animation).
 *
 * It animates on mount and whenever `target` changes. In practice each ranked
 * card is re-keyed per response, so this runs exactly once per set of results
 * and never re-triggers on an unrelated re-render.
 */
export function useCountUp(target: number, durationMs = 500): number {
  const reduce = prefersReducedMotion()
  const [raw, setRaw] = useState(0)

  useEffect(() => {
    if (reduce) return
    let raf = 0
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs)
      const eased = 1 - Math.pow(1 - t, 3) // easeOutCubic
      setRaw(target * eased)
      if (t < 1) raf = requestAnimationFrame(tick)
      else setRaw(target)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, durationMs, reduce])

  return reduce ? target : raw
}
