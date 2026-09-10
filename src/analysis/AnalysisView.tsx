import { useMemo, useState } from 'react'
import './analysis.css'
import { getMunicipality } from '../data/municipalities'
import { CustomizePanel } from './CustomizePanel'
import { DevCatalogue } from './DevCatalogue'
import { RankedPlanCard } from './RankedPlanCard'
import { useRanking } from './useRanking'
import {
  EMPTY_CUSTOMIZATION,
  clearCustomizationField,
  customizationChips,
  customizationIsActive,
  type Customization,
} from './customization'
import type { RankingPreset } from '../api/types'

interface Props {
  /** The confirmed municipality id (null only if something went wrong upstream). */
  municipalityId: string | null
  /** Return to the miniature map from the start. */
  onBack: () => void
}

const PRESETS: { id: RankingPreset; label: string; blurb: string }[] = [
  {
    id: 'overall',
    label: 'Best Overall',
    blurb: 'A balance of price, data, technology, features, roaming and current offers.',
  },
  {
    id: 'students',
    label: 'Best for Students',
    blurb: 'Leans toward what usually matters most on a student budget.',
  },
  {
    id: 'cheapest',
    label: 'Cheapest',
    blurb: 'Lowest monthly price — nothing else taken into account.',
  },
  {
    id: 'most_data',
    label: 'Most Data',
    blurb: 'The most full-speed data at home; genuinely unlimited plans first.',
  },
  {
    id: 'offers',
    label: 'Best Current Offers',
    blurb: 'Only plans with a verified saving on their regular price, strongest saving first.',
  },
]

/**
 * The V1 results screen: Top 5 plans for the selected municipality, powered
 * entirely by the backend ranking engine (`GET /api/rank`). Preset tabs switch
 * ranking modes; the Customize panel collects filter preferences that the
 * backend applies. Nothing is ranked or filtered in the browser.
 */
export function AnalysisView({ municipalityId, onBack }: Props) {
  const placeName = useMemo(
    () =>
      (municipalityId ? getMunicipality(municipalityId)?.name : null) ??
      'Metro Vancouver',
    [municipalityId],
  )

  const [preset, setPreset] = useState<RankingPreset>('overall')
  const [showCatalogue, setShowCatalogue] = useState(false)

  // One shared customization state. `committed` drives the request; `draft` is
  // what the panel edits until the user presses Apply.
  const [committed, setCommitted] = useState<Customization>(EMPTY_CUSTOMIZATION)
  const [draft, setDraft] = useState<Customization>(EMPTY_CUSTOMIZATION)
  const [panelOpen, setPanelOpen] = useState(false)

  const ranking = useRanking({ preset, municipalityId, customization: committed })
  const activePreset = PRESETS.find((p) => p.id === preset)!
  const chips = customizationChips(committed)
  const isCustomized = customizationIsActive(committed)

  const openPanel = () => {
    setDraft(committed)
    setPanelOpen(true)
  }
  const applyDraft = () => {
    setCommitted(draft)
    setPanelOpen(false)
  }
  const resetAll = () => {
    setCommitted(EMPTY_CUSTOMIZATION)
    setDraft(EMPTY_CUSTOMIZATION)
  }
  const removeChip = (key: keyof Customization) => {
    const next = clearCustomizationField(committed, key)
    setCommitted(next)
    setDraft(next)
  }
  // The standalone student checkbox and the panel's student toggle share one
  // value — toggling either keeps both (and the request) in sync.
  const setStudentEligible = (v: boolean) => {
    setCommitted((c) => ({ ...c, studentEligible: v }))
    setDraft((d) => ({ ...d, studentEligible: v }))
  }

  return (
    <div className="analysis-root">
      <div className="analysis-inner">
        <header className="analysis-header">
          <p className="analysis-place-line">Best plans for {placeName}</p>
          <h1 className="analysis-title">
            <span className="analysis-place">
              {isCustomized ? 'Top plans' : 'Top 5 plans'}
            </span>{' '}
            <span className="analysis-kicker">{activePreset.label}</span>
          </h1>
          <p className="analysis-meta">
            <span>{activePreset.blurb}</span>
          </p>
        </header>

        <nav className="rank-tabs" aria-label="Ranking mode">
          {PRESETS.map((p) => (
            <button
              key={p.id}
              type="button"
              className={`rank-tab${p.id === preset ? ' rank-tab--active' : ''}`}
              aria-pressed={p.id === preset}
              onClick={() => setPreset(p.id)}
            >
              {p.label}
            </button>
          ))}
        </nav>

        <div className="rank-controls">
          <button
            type="button"
            className={`rank-customize-btn${isCustomized ? ' rank-customize-btn--on' : ''}`}
            aria-expanded={panelOpen}
            onClick={() => (panelOpen ? setPanelOpen(false) : openPanel())}
          >
            {isCustomized && !panelOpen
              ? `Customize · ${chips.length} active`
              : 'Customize'}
          </button>

          {isCustomized && !panelOpen && (
            <div className="rank-summary" role="group" aria-label="Active filters">
              <span className="rank-summary__tag">Customized</span>
              {chips.map((chip) => (
                <button
                  key={chip.key}
                  type="button"
                  className="rank-chip"
                  onClick={() => removeChip(chip.key)}
                  aria-label={`Remove filter: ${chip.label}`}
                >
                  {chip.label}
                  <span aria-hidden className="rank-chip__x">
                    &times;
                  </span>
                </button>
              ))}
              <button
                type="button"
                className="rank-summary__clear"
                onClick={resetAll}
              >
                Clear all
              </button>
            </div>
          )}
        </div>

        {panelOpen && (
          <CustomizePanel
            draft={draft}
            committed={committed}
            onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))}
            onApply={applyDraft}
            onResetAll={resetAll}
            onClose={() => setPanelOpen(false)}
          />
        )}

        {preset === 'students' && (
          <div className="rank-student">
            <label className="rank-student__toggle">
              <input
                type="checkbox"
                checked={committed.studentEligible}
                onChange={(e) => setStudentEligible(e.target.checked)}
              />
              <span>I'm eligible for post-secondary student offers</span>
            </label>
            <p className="rank-student__note">
              {committed.studentEligible
                ? 'Verified student pricing is being used where a carrier offers it. Carriers require proof of enrollment at a recognized post-secondary institution. (You can also change this in Customize.)'
                : 'Off by default — choosing this ranking does not assume you are a student. Turn it on only if you can meet the carriers’ student requirements; student-only offers from Koodo and Freedom can then be included.'}
            </p>
          </div>
        )}

        {ranking.status === 'loading' && (
          <div className="rank-state" role="status">
            <span className="rank-state__spinner" aria-hidden />
            Finding the best plans for {placeName}…
          </div>
        )}

        {ranking.status === 'error' && (
          <div className="rank-state rank-state--error" role="alert">
            <p className="rank-state__title">We couldn’t load the ranking</p>
            <p className="rank-state__detail">{ranking.message}</p>
            <p className="rank-state__hint">
              This is a live comparison — results aren’t shown from an older cached
              copy when the service can’t be reached. Please try again in a moment.
            </p>
            <button type="button" className="analysis-back" onClick={ranking.reload}>
              Try again
            </button>
          </div>
        )}

        {ranking.status === 'ready' && (
          <>
            {ranking.data.results.length === 0 ? (
              <div className="rank-state rank-state--empty">
                {isCustomized ? (
                  <>
                    <p className="rank-state__title">No plans match these preferences</p>
                    <p>Try changing or clearing one of your filters.</p>
                    <ul className="rank-state__filters">
                      {chips.map((chip) => (
                        <li key={chip.key}>{chip.label}</li>
                      ))}
                    </ul>
                    <button
                      type="button"
                      className="analysis-back"
                      onClick={resetAll}
                    >
                      Reset filters
                    </button>
                  </>
                ) : preset === 'offers' ? (
                  <p>
                    No current offers right now — no plan has a verified saving
                    against its regular price.
                  </p>
                ) : (
                  <p>No plans are available for this ranking right now.</p>
                )}
              </div>
            ) : (
              <>
                <p className="rank-considered">
                  {ranking.refreshing && (
                    <span className="rank-considered__spinner" aria-hidden />
                  )}
                  {ranking.refreshing
                    ? 'Updating…'
                    : isCustomized
                      ? ranking.data.candidate_count > ranking.data.results.length
                        ? `Showing the top ${ranking.data.results.length} of ${ranking.data.candidate_count} plans that match your preferences`
                        : `${ranking.data.candidate_count} plan${
                            ranking.data.candidate_count === 1 ? '' : 's'
                          } match your preferences (out of ${ranking.data.pre_filter_candidate_count} available)`
                      : `Showing the top ${ranking.data.results.length} of ${ranking.data.candidate_count} available plans`}
                  {!ranking.refreshing && (
                    <>
                      {' · '}your selected area doesn’t change these results
                    </>
                  )}
                </p>
                <div
                  className={`rank-list${ranking.refreshing ? ' rank-list--refreshing' : ''}`}
                  aria-busy={ranking.refreshing}
                >
                  {ranking.data.results.map((r) => (
                    <RankedPlanCard key={r.plan_id} ranked={r} preset={preset} />
                  ))}
                </div>
              </>
            )}
          </>
        )}

        {import.meta.env.DEV && (
          <section className="analysis-section analysis-section--catalogue">
            <button
              type="button"
              className="rank-catalogue-toggle"
              aria-expanded={showCatalogue}
              onClick={() => setShowCatalogue((v) => !v)}
            >
              {showCatalogue ? '▾' : '▸'} Full plan catalogue
            </button>
            {showCatalogue && (
              <div className="analysis-catalogue-body">
                <DevCatalogue municipalityId={municipalityId} />
              </div>
            )}
          </section>
        )}

        <button type="button" className="analysis-back" onClick={onBack}>
          ← Back to the map
        </button>

        <p className="analysis-disclaimer">
          Carrier names are used only to identify each provider's plans. This is
          an independent comparison and is not affiliated with, authorized by, or
          endorsed by Chatr, Bell, Koodo, Freedom Mobile, or their parent
          networks.
        </p>
      </div>
    </div>
  )
}
