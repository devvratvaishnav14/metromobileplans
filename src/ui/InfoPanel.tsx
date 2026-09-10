import { useEffect, useRef } from 'react'
import { useIsTouch } from './useIsTouch'

interface Props {
  onClose: () => void
}

/**
 * Polished system-style overlay explaining how to use the map. Light backdrop
 * (the 3D world stays visible), close X, Escape to dismiss, and a small focus
 * trap so keyboard users stay inside the dialog while it is open.
 */
export function InfoPanel({ onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const isTouch = useIsTouch()

  useEffect(() => {
    closeRef.current?.focus()

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key !== 'Tab' || !panelRef.current) return
      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'button, a[href], [tabindex]:not([tabindex="-1"])',
      )
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const steps = [
    isTouch
      ? 'Drag to move around the Metro Vancouver map.'
      : 'Move around the Metro Vancouver map.',
    isTouch
      ? 'Tap an area to see its name.'
      : 'Hover over an area to see its name.',
    isTouch
      ? "Tap the area where you'll use your plan most."
      : "Click the area where you'll use your plan most.",
    'Follow the route as the character travels there.',
    "We'll compare and rank the best mobile plans for that location.",
  ]

  return (
    <div className="info-backdrop" onClick={onClose}>
      <div
        ref={panelRef}
        className="info-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="info-panel-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="info-panel__head">
          <h2 id="info-panel-title" className="info-panel__title">
            How to use the map
          </h2>
          <button
            ref={closeRef}
            type="button"
            className="info-panel__close"
            onClick={onClose}
            aria-label="Close"
          >
            &times;
          </button>
        </div>
        <ol className="info-panel__list">
          {steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </div>
    </div>
  )
}
