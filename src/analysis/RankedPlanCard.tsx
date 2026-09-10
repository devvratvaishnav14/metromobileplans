import { useId, useState } from 'react'
import type { RankedPlan, RankingPreset } from '../api/types'
import { providerBrand } from './providers'
import {
  componentRows,
  offerSummary,
  planFactRows,
  priceDisplay,
  roamingScopeLabel,
  scoreText,
  shortDataLabel,
} from './rankingFormat'

interface Props {
  ranked: RankedPlan
  preset: RankingPreset
}

const SOURCE_LABEL: Record<string, string> = {
  official_automated: 'Official carrier source',
  official_manual: 'Official carrier source, checked by hand',
  trusted_secondary: 'Third-party source',
}

function ScoreBar({ score }: { score: number | null }) {
  if (score == null) {
    return (
      <span className="rank-breakdown__value rank-breakdown__value--na">
        not enough data
      </span>
    )
  }
  return (
    <span className="rank-breakdown__meter" aria-hidden>
      <span
        className="rank-breakdown__fill"
        style={{ width: `${Math.max(0, Math.min(100, score))}%` }}
      />
    </span>
  )
}

export function RankedPlanCard({ ranked, preset }: Props) {
  const [open, setOpen] = useState(false)
  const detailId = useId()
  const plan = ranked.plan
  const brand = providerBrand(ranked.provider_slug)
  const price = priceDisplay(ranked)
  const offer = preset === 'offers' ? offerSummary(ranked) : null
  const reason = ranked.reasons.join(' · ')
  const someUnscored = componentRows(ranked).some((row) => row.score == null)

  return (
    <article className="rank-card">
      <div className="rank-card__head">
        <div className="rank-card__rank" aria-label={`Rank ${ranked.rank}`}>
          <span className="rank-card__rank-hash">#</span>
          {ranked.rank}
        </div>

        <div className="rank-card__identity">
          <div className="rank-card__brand">
            {brand?.mark && (
              <img
                className="rank-card__logo"
                src={brand.mark}
                alt=""
                width={28}
                height={28}
                loading="lazy"
                decoding="async"
              />
            )}
            <span className="rank-card__brand-text">
              <span className="rank-card__provider">
                {brand?.name ?? ranked.provider_name}
              </span>
              {brand?.network && (
                <span className="rank-card__network">{brand.network}</span>
              )}
            </span>
          </div>
          <h3 className="rank-card__name">{ranked.plan_name ?? ranked.external_id}</h3>
          <p className="rank-card__data">{shortDataLabel(plan)}</p>
          <div className="rank-card__chips">
            {plan.network_technology && (
              <span className="rank-card__chip">{plan.network_technology}</span>
            )}
            <span className="rank-card__chip">{roamingScopeLabel(plan)}</span>
            {plan.canada_wide_calling === true && (
              <span className="rank-card__chip">Unlimited Canada-wide talk</span>
            )}
          </div>
        </div>

        <div className="rank-card__price">
          <span className="rank-card__amount">{price.amount}</span>
          <span className="rank-card__unit">{price.unit}</span>
          {price.qualifier && (
            <span className="rank-card__qualifier">{price.qualifier}</span>
          )}
        </div>
      </div>

      {/* On Best Current Offers the offer block below already states the
          regular → applicable price and its conditions, so the generic
          "as low as" tier line would just repeat it. */}
      {price.disclosures.length > 0 && !offer && (
        <ul className="rank-card__disclosures">
          {price.disclosures.map((d) => (
            <li key={d}>{d}</li>
          ))}
        </ul>
      )}

      {ranked.eligibility_note && (
        <p className="rank-card__eligibility">
          Eligibility applies — {ranked.eligibility_note}
        </p>
      )}

      {offer && (
        <div className="rank-card__offer">
          <p className="rank-card__offer-line">
            <span className="rank-card__offer-was">{offer.regular}/mo</span>
            <span className="rank-card__offer-arrow">→</span>
            <span className="rank-card__offer-now">{offer.applicable}/mo</span>
            <span className="rank-card__offer-tier">{offer.tierPhrase}</span>
          </p>
          <p className="rank-card__offer-save">
            Save {offer.dollarSavings}/mo ({offer.percentSavings}) vs the regular price
          </p>
          {offer.conditions.length > 0 && (
            <p className="rank-card__offer-conds">Requires: {offer.conditions.join('; ')}</p>
          )}
        </div>
      )}

      {reason && <p className="rank-card__reason">{reason}</p>}

      <div className="rank-card__score">
        <div className="rank-card__score-num">
          <span className="rank-card__score-label">Overall score</span>
          <span className="rank-card__score-value">{scoreText(ranked.final_score)}</span>
        </div>
        <span className="rank-card__score-src">
          Calculated from verified plan data — based on price, data, technology,
          features, roaming and current offers
        </span>
      </div>

      <button
        type="button"
        className="rank-card__toggle"
        aria-expanded={open}
        aria-controls={detailId}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? 'Hide the details' : 'Why this ranks here · plan details'}
      </button>

      <div id={detailId} className="rank-card__detail" hidden={!open}>
        <h4 className="rank-card__detail-title">Score breakdown</h4>
        <p className="rank-card__detail-sub">
          Each part is scored out of 100 from verified plan data. How much each
          part counts toward the overall score depends on the ranking mode you
          picked.
        </p>
        <dl className="rank-breakdown">
          {componentRows(ranked).map((row) => (
            <div key={row.key} className="rank-breakdown__row">
              <dt>{row.label}</dt>
              <dd>
                <ScoreBar score={row.score} />
                {row.score != null && (
                  <span className="rank-breakdown__value">{row.score.toFixed(1)}</span>
                )}
              </dd>
            </div>
          ))}
        </dl>
        {someUnscored && (
          <p className="rank-card__detail-note">
            “Not enough data” means the carrier hasn’t published that detail for
            this plan — the other parts count for more, so the plan isn’t marked
            down for it.
          </p>
        )}

        <h4 className="rank-card__detail-title">This plan</h4>
        <dl className="rank-facts">
          {planFactRows(ranked).map((row) => (
            <div key={row.label} className="rank-facts__row">
              <dt>{row.label}</dt>
              <dd>{row.value}</dd>
            </div>
          ))}
        </dl>

        <p className="rank-card__provenance">
          {SOURCE_LABEL[plan.source_mode] ?? 'Source'}
          {' · '}
          <a href={plan.source_url} target="_blank" rel="noreferrer noopener">
            view carrier page
          </a>
          {' · '}
          {plan.freshness_label}
        </p>
      </div>
    </article>
  )
}
