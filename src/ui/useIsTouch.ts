import { useSyncExternalStore } from 'react'

const QUERY = '(hover: none) and (pointer: coarse)'

/**
 * True on touch-first devices (phones, tablets) so the UI can swap
 * mouse-specific wording ("Click") for touch wording ("Tap").
 */
export function useIsTouch(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const mql = window.matchMedia(QUERY)
      mql.addEventListener('change', cb)
      return () => mql.removeEventListener('change', cb)
    },
    () => window.matchMedia(QUERY).matches,
    () => false,
  )
}
