import { useEffect, useRef } from 'react'
import { SUPPORTED_MUNICIPALITY_IDS } from '../data/coverage'
import { getMunicipality } from '../data/municipalities'

interface Props {
  onClose: () => void
}

const AREAS = SUPPORTED_MUNICIPALITY_IDS.map(
  (id) => getMunicipality(id)?.name ?? id,
).join(', ')

/**
 * A short "About this project" note. Reuses the lightweight dialog styling from
 * "How rankings work" (.hrw-*). Concise — not a biography, no contact details.
 */
export function AboutProject({ onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="hrw-overlay" onClick={onClose} role="presentation">
      <div
        className="hrw-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="about-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="hrw-head">
          <h2 id="about-title" className="hrw-title">About this project</h2>
          <button
            ref={closeRef}
            type="button"
            className="hrw-close"
            onClick={onClose}
            aria-label="Close"
          >
            &times;
          </button>
        </div>

        <div className="hrw-body">
          <p>
            Metro Mobile Plans was built by <strong>Devvrat Vaishnav</strong> (BSc
            in Data Science, SFU) as an independent project.
          </p>
          <ul>
            <li>
              It compares <strong>verified mobile-plan data</strong> collected
              from official carrier sources.
            </li>
            <li>
              Rankings are <strong>deterministic</strong> — produced by the
              site’s own scoring model, not by AI, and the same data always
              gives the same order.
            </li>
            <li>
              V1 currently supports <strong>{AREAS}</strong>. The selected area
              is context only; it does not change the ranking.
            </li>
          </ul>
        </div>
      </div>
    </div>
  )
}
