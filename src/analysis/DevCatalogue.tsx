import { useMemo } from 'react'
import { PlanCard } from './PlanCard'
import { useAnalysis } from './useAnalysis'
import type { Plan } from '../api/types'

/**
 * The full development catalogue (all verified + secondary plans, unranked,
 * sorted by price). Not the normal V1 experience — kept accessible behind a
 * toggle for debugging and provenance inspection.
 */
export function DevCatalogue({ municipalityId }: { municipalityId: string | null }) {
  const analysis = useAnalysis(municipalityId)

  const grouped = useMemo(() => {
    if (analysis.status !== 'ready') return null
    const ranked: Plan[] = []
    const secondary: Plan[] = []
    for (const p of analysis.data.plans) {
      ;(p.is_rankable ? ranked : secondary).push(p)
    }
    return { ranked, secondary }
  }, [analysis])

  if (analysis.status === 'loading') {
    return <p className="analysis-status">Loading the development catalogue…</p>
  }
  if (analysis.status === 'error') {
    return (
      <div className="analysis-status analysis-status--error">
        <p>{analysis.message}</p>
        <button type="button" className="analysis-back" onClick={analysis.reload}>
          Retry
        </button>
      </div>
    )
  }
  if (!grouped) return null

  return (
    <>
      <p className="analysis-section__sub">
        {analysis.data.meta.freshness_label} · {grouped.ranked.length} verified &amp;
        ranking-eligible · {grouped.secondary.length} secondary / unverified. Sorted
        by current price — this is not a ranking.
      </p>
      <div className="analysis-plans">
        {grouped.ranked.map((plan) => (
          <PlanCard key={plan.id} plan={plan} />
        ))}
      </div>
      {grouped.secondary.length > 0 && (
        <>
          <h3 className="analysis-section__title" style={{ marginTop: 24 }}>
            Secondary / not officially verified
            <span className="analysis-section__count">{grouped.secondary.length}</span>
          </h3>
          <div className="analysis-plans">
            {grouped.secondary.map((plan) => (
              <PlanCard key={plan.id} plan={plan} />
            ))}
          </div>
        </>
      )}
    </>
  )
}
