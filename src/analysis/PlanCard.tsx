import { useState } from 'react'
import type { Plan } from '../api/types'
import { dataLabel, detailRows, priceCaveat, priceLabel, wasPriceLabel } from './format'

interface Props {
  plan: Plan
}

const MODE_TAG: Record<string, string> = {
  official_automated: 'Official · auto',
  official_manual: 'Official · manually verified',
  trusted_secondary: 'Third-party source',
}

function heldOutReason(plan: Plan): string | null {
  if (plan.is_rankable) return null
  if (plan.eligibility_restricted)
    return plan.eligibility_conditions
      ? `restricted offer — only for: ${plan.eligibility_conditions}`
      : 'restricted offer — not available to an ordinary customer'
  if (plan.verification_status === 'stale')
    return 'verification is stale — needs re-verification'
  if (plan.verification_status === 'secondary_confirmed')
    return 'third-party source — not ranking-eligible without an official cross-check'
  const missing = plan.issues
    .find((i) => i.message.startsWith('not rankable'))
    ?.message.replace('not rankable -- missing: ', 'missing ')
  return missing ?? 'incomplete verified data'
}

/** Badge tone keyed to verification, not just freshness. Secondary-only plans
 * are NEVER green. */
function pillTone(plan: Plan): 'verified' | 'stale' | 'secondary' | 'provisional' {
  switch (plan.verification_status) {
    case 'verified':
      return 'verified'
    case 'stale':
    case 'invalid':
      return 'stale'
    case 'secondary_confirmed':
      return 'secondary'
    default:
      return 'provisional'
  }
}

function offerEndLabel(plan: Plan): string | null {
  if (!plan.is_current_offer) return null
  if (plan.promo_ends_at) {
    const d = new Date(plan.promo_ends_at)
    if (!Number.isNaN(d.getTime())) return `ends ${d.toLocaleDateString()}`
  }
  if (plan.promo_expiry_known === false) return 'limited time'
  return null
}

export function PlanCard({ plan }: Props) {
  const [open, setOpen] = useState(false)
  const price = priceLabel(plan)
  const was = wasPriceLabel(plan)
  const caveat = priceCaveat(plan)
  const badge =
    typeof plan.attributes?.badge === 'string' ? (plan.attributes.badge as string) : null
  const offerEnds = offerEndLabel(plan)

  const chips: string[] = []
  if (plan.plan_type) chips.push(plan.plan_type)
  if (plan.network_technology) chips.push(plan.network_technology)
  else if (plan.network_speed_tier) chips.push(plan.network_speed_tier)
  if (plan.canada_wide_calling === true) chips.push('Unlimited Canada-wide talk')
  if (plan.unlimited_text === true) chips.push('Unlimited text')
  if (plan.includes_us === true) chips.push('US usage')
  if (plan.esim === true) chips.push('eSIM')
  if (plan.contract_required === false) chips.push('No contract')

  return (
    <article className={`plan-card${plan.is_rankable ? '' : ' plan-card--flagged'}`}>
      <div className="plan-card__head">
        <div className="plan-card__price">
          {price ? (
            <>
              <span className="plan-card__amount">{price.amount}</span>
              <span className="plan-card__unit">{price.unit}</span>
              {was && <span className="plan-card__was">{was}</span>}
            </>
          ) : (
            <span className="plan-card__amount plan-card__amount--none">price unknown</span>
          )}
        </div>

        <div className="plan-card__identity">
          <h3 className="plan-card__name">
            {plan.plan_name ?? plan.external_id}
            {plan.is_current_offer && (
              <span className="plan-card__offer">
                Offer
                {plan.offer_savings_cad != null && ` · save $${plan.offer_savings_cad}`}
                {offerEnds && ` · ${offerEnds}`}
              </span>
            )}
            {!plan.is_current_offer && badge && (
              <span className="plan-card__deal">{badge}</span>
            )}
          </h3>
          <p className="plan-card__data">{dataLabel(plan)}</p>
          <div className="plan-card__chips">
            {chips.map((c) => (
              <span key={c} className="plan-card__chip">
                {c}
              </span>
            ))}
          </div>
        </div>

        <div className="plan-card__freshness">
          <span className={`plan-card__pill plan-card__pill--${pillTone(plan)}`}>
            {plan.freshness_label}
          </span>
          <span className="plan-card__provider">{plan.provider_name}</span>
        </div>
      </div>

      <p className="plan-card__provenance">
        <span className={`plan-card__mode plan-card__mode--${plan.source_mode}`}>
          {MODE_TAG[plan.source_mode] ?? plan.source_mode}
        </span>
        {plan.verified_by && <span> · verified by {plan.verified_by}</span>}
        {plan.official_crosscheck && <span> · official cross-check</span>}
        <span>
          {' '}·{' '}
          <a href={plan.source_url} target="_blank" rel="noreferrer noopener">
            source
          </a>
        </span>
      </p>

      {caveat && (
        <p className="plan-card__note plan-card__note--price">{caveat}.</p>
      )}

      {plan.offer_note && (
        <p className="plan-card__note plan-card__note--offer">{plan.offer_note}.</p>
      )}

      {!plan.is_rankable && (
        <p className="plan-card__note">
          Held out of ranked results — {heldOutReason(plan)}.
        </p>
      )}

      <button
        type="button"
        className="plan-card__toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? 'Hide details' : 'All details, conditions & source'}
      </button>

      {open && (
        <div className="plan-card__detail">
          <dl className="plan-card__rows">
            {detailRows(plan).map(([k, v]) => (
              <div key={k} className="plan-card__row">
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>

          {plan.issues.length > 0 && (
            <ul className="plan-card__issues">
              {plan.issues.map((i, idx) => (
                <li key={idx} className={`plan-card__issue plan-card__issue--${i.severity}`}>
                  {i.field ? `${i.field}: ` : ''}
                  {i.message}
                </li>
              ))}
            </ul>
          )}

          <p className="plan-card__source">
            Source:{' '}
            <a href={plan.source_url} target="_blank" rel="noreferrer noopener">
              {plan.source_url.replace(/^https?:\/\//, '')}
            </a>{' '}
            · fetched {new Date(plan.fetched_at).toLocaleString()} · provider id{' '}
            <code>{plan.external_id}</code>
          </p>
        </div>
      )}
    </article>
  )
}
