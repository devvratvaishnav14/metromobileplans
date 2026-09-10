import { useState } from 'react'

interface Props {
  placeName: string
  onConfirm: () => void
  onReject: () => void
}

/** ms for the card's slide-out before the flow actually advances. */
const DISMISS_MS = 340

/**
 * Right-side confirmation notification shown once the boy has arrived and
 * settled. Same system-notification styling as the onboarding stack. Its own
 * buttons capture clicks; the rest of the map stays interactive.
 *
 * Mounted with `key={destinationId}` by the parent, so each new arrival gets a
 * fresh instance (and a clean slide-in).
 */
export function ConfirmationNotification({ placeName, onConfirm, onReject }: Props) {
  const [leaving, setLeaving] = useState<'yes' | 'no' | null>(null)

  const dismissThen = (choice: 'yes' | 'no', done: () => void) => {
    if (leaving) return
    setLeaving(choice)
    window.setTimeout(done, DISMISS_MS)
  }

  return (
    <div className="confirm-stack">
      <div
        className={`onb-card confirm-card${leaving ? ' confirm-card--out' : ''}`}
        role="dialog"
        aria-label={`Use ${placeName} for your plan search?`}
      >
        <div className="onb-card__head">
          <span className="onb-card__dot" aria-hidden="true" />
          <span className="onb-card__app">Metro Mobile Plans</span>
          <span className="onb-card__time">now</span>
        </div>
        <p className="onb-card__title">Use {placeName} for your plan search?</p>
        <div className="confirm-card__actions">
          <button
            type="button"
            className="confirm-btn confirm-btn--primary"
            onClick={() => dismissThen('yes', onConfirm)}
          >
            Yes
          </button>
          <button
            type="button"
            className="confirm-btn confirm-btn--secondary"
            onClick={() => dismissThen('no', onReject)}
          >
            Choose another area
          </button>
        </div>
      </div>
    </div>
  )
}
