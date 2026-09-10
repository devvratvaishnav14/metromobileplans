import { useState } from 'react'
import { supportedMunicipalityNames } from '../data/coverage'

interface Props {
  /** The unsupported municipality the user clicked. */
  placeName: string
  onDismiss: () => void
}

/** ms for the card's slide-out before it unmounts. Matches `.confirm-card--out`. */
const DISMISS_MS = 340

/**
 * Shown when the user clicks a municipality outside V1 coverage. Same
 * system-notification styling as the arrival confirmation. The rest of the map
 * stays interactive — dismissing just returns the user to browsing.
 *
 * Mounted with `key={comingSoon.id}` by the parent, so clicking a different
 * unsupported area gives a fresh card.
 */
export function ComingSoonNotification({ placeName, onDismiss }: Props) {
  const [leaving, setLeaving] = useState(false)

  const dismiss = () => {
    if (leaving) return
    setLeaving(true)
    window.setTimeout(onDismiss, DISMISS_MS)
  }

  return (
    <div className="confirm-stack">
      <div
        className={`onb-card confirm-card${leaving ? ' confirm-card--out' : ''}`}
        role="dialog"
        aria-label={`Plan analysis for ${placeName} is not available yet`}
      >
        <div className="onb-card__head">
          <span className="onb-card__dot" aria-hidden="true" />
          <span className="onb-card__app">Metro Mobile Plans</span>
          <span className="onb-card__time">now</span>
        </div>
        <p className="onb-card__title">Coverage coming soon</p>
        <p className="onb-card__body">
          We&rsquo;re expanding plan analysis to {placeName}.{' '}
          {supportedMunicipalityNames()} are available right now.
        </p>
        <div className="confirm-card__actions">
          <button
            type="button"
            className="confirm-btn confirm-btn--primary"
            onClick={dismiss}
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  )
}
