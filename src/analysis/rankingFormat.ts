/**
 * Display helpers for ranked plans. These format numbers the backend already
 * computed — they never rank, re-weight, or recompute a component score.
 */
import type { Plan, RankedPlan } from '../api/types'
import { dataLabel } from './format'

export function money(n: number): string {
  return `$${Number.isInteger(n) ? n : n.toFixed(2)}`
}

function gb(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1)
}

/**
 * A short, headline-friendly data summary for the card. The full throttle-speed
 * detail (which can be a long sentence) is kept for the expanded view only.
 */
export function shortDataLabel(plan: Plan): string {
  const cap = plan.data_full_speed_gb ?? plan.data_total_gb ?? plan.data_base_gb
  if (plan.data_unlimited_is_full_speed) return 'Unlimited full-speed data'
  if (plan.data_unlimited && cap != null)
    return `${gb(cap)} GB full-speed, then unlimited at reduced speed`
  if (plan.data_unlimited) return 'Unlimited data'
  if (cap != null) return `${gb(cap)} GB full-speed data`
  if (plan.data_unlimited === false) return 'No data — talk & text only'
  return 'Data amount not stated'
}

function tierConditionPhrase(label: string, conditions: string[]): string {
  const text = conditions.join(' ').toLowerCase()
  if (label === 'with bundle') return 'with a qualifying bundle'
  if (label === 'with AutoPay') {
    return text.includes('digital discount')
      ? 'with the Digital Discount'
      : 'with AutoPay'
  }
  if (label === 'promotional') return 'with promotional pricing'
  return `(${label})`
}

export interface PriceDisplay {
  /** The prominent number, e.g. "$13.25". */
  amount: string
  /** "/mo". */
  unit: string
  /** Sits beside the amount: "equivalent", "Eligible student price", or null. */
  qualifier: string | null
  /** Honest secondary lines shown under the price. */
  disclosures: string[]
}

/**
 * The price to show prominently + the disclosures that must accompany it.
 * Never presents a monthly-equivalent (annual) price on its own, and never
 * hides that a lower price needs a condition.
 */
export function priceDisplay(r: RankedPlan): PriceDisplay {
  const used = r.price_used_cad
  const reference = r.regular_reference_price_cad
  const disclosures: string[] = []

  if (r.commitment) {
    disclosures.push(
      `${money(r.commitment.upfront_cad)} paid upfront for ${r.commitment.term_months} months`,
    )
    return {
      amount: money(r.monthly_equivalent_price_cad ?? used ?? 0),
      unit: '/mo',
      qualifier: 'equivalent',
      disclosures,
    }
  }

  const isStudentPrice = (r.applicable_tier_label ?? '')
    .toLowerCase()
    .includes('student')
  if (isStudentPrice && used != null && reference != null) {
    disclosures.push(`Regular price ${money(reference)}/mo`)
    return {
      amount: money(used),
      unit: '/mo',
      qualifier: 'Eligible student price',
      disclosures,
    }
  }

  // A regular ranking price is being used — surface any cheaper conditional tier
  // as a secondary "as low as" line so the condition is never hidden.
  const cheaper = r.plan.price_tiers
    .filter((t) => t.label !== 'regular' && used != null && t.amount < used)
    .sort((a, b) => a.amount - b.amount)
  if (cheaper.length) {
    const t = cheaper[0]
    disclosures.push(
      `As low as ${money(t.amount)}/mo ${tierConditionPhrase(t.label, t.conditions)}`,
    )
    disclosures.push(
      "Regular price shown by default — conditions like this aren't assumed.",
    )
  }

  return { amount: money(used ?? 0), unit: '/mo', qualifier: null, disclosures }
}

export interface ComponentRow {
  key: string
  label: string
  /** 0–100, straight from the backend. null = there wasn't enough verified data
   *  to score this part for this plan. */
  score: number | null
}

export function componentRows(r: RankedPlan): ComponentRow[] {
  return [
    { key: 'price', label: 'Price', score: r.price_score },
    { key: 'data', label: 'Data', score: r.data_score },
    { key: 'technology', label: 'Technology', score: r.technology_score },
    { key: 'features', label: 'Features', score: r.features_score },
    { key: 'roaming', label: 'Roaming', score: r.roaming_score },
    { key: 'offer', label: 'Offer', score: r.offer_score },
  ]
}

const YES_NO = (v: boolean | null): string | null =>
  v === true ? 'Yes' : v === false ? 'No' : null

export interface FactRow {
  label: string
  value: string
}

/** Plain-language facts for the expanded card. Deliberately a small, curated
 *  set — no provenance / verification internals (those are dev-only). */
export function planFactRows(r: RankedPlan): FactRow[] {
  const p = r.plan
  const rows: Array<FactRow | null> = []

  if (r.price_used_cad != null)
    rows.push({ label: 'Price used here', value: `${money(r.price_used_cad)}/mo` })
  if (
    r.regular_reference_price_cad != null &&
    r.regular_reference_price_cad !== r.price_used_cad
  )
    rows.push({
      label: 'Regular monthly price',
      value: `${money(r.regular_reference_price_cad)}/mo`,
    })
  if (r.commitment)
    rows.push({
      label: 'Paid upfront',
      value: `${money(r.commitment.upfront_cad)} for ${r.commitment.term_months} months`,
    })

  rows.push({ label: 'Full-speed data', value: dataLabel(p) })
  rows.push({ label: 'Network', value: p.network_technology ?? 'Not stated' })
  rows.push({ label: 'Roaming', value: roamingScopeLabel(p) })
  rows.push({
    label: 'Talk',
    value:
      p.canada_wide_calling === true
        ? 'Unlimited Canada-wide'
        : p.canada_wide_calling === false
          ? 'Limited / metered'
          : 'Not stated',
  })
  const text = YES_NO(p.unlimited_text)
  if (text) rows.push({ label: 'Unlimited text', value: text })
  const hotspot = YES_NO(p.hotspot)
  if (hotspot)
    rows.push({
      label: 'Hotspot / tethering',
      value:
        p.hotspot === true && p.hotspot_data_gb != null
          ? `Yes (${gb(p.hotspot_data_gb)} GB)`
          : hotspot,
    })
  const contract = YES_NO(p.contract_required)
  if (contract) rows.push({ label: 'Contract required', value: contract })

  if (r.offer_detail)
    rows.push({
      label: 'Current saving',
      value: `${money(r.offer_detail.dollar_savings_cad)}/mo (${Math.round(
        r.offer_detail.percent_savings * 100,
      )}%) ${tierConditionPhrase(r.offer_detail.tier_label, offerTierConditions(r))}`,
    })

  return rows.filter((x): x is FactRow => x != null)
}

function offerTierConditions(r: RankedPlan): string[] {
  const d = r.offer_detail
  if (!d) return []
  return r.plan.price_tiers.find((t) => t.label === d.tier_label)?.conditions ?? []
}

/** Short factual roaming scope, for the card and the breakdown. */
export function roamingScopeLabel(plan: Plan): string {
  if (plan.includes_us && plan.includes_mexico) return 'Canada · US · Mexico'
  if (plan.includes_us) return 'Canada · US'
  if (plan.international_roaming) return 'International roaming included'
  return 'Canada only'
}

export interface OfferSummary {
  regular: string
  applicable: string
  tierPhrase: string
  dollarSavings: string
  percentSavings: string
  /** The plan's own stated conditions for this tier (verbatim from the source). */
  conditions: string[]
}

/** The offer facts to show on a Best Current Offers card (no internal
 *  multipliers — those live only in the detailed score breakdown). */
export function offerSummary(r: RankedPlan): OfferSummary | null {
  const d = r.offer_detail
  if (!d || r.regular_reference_price_cad == null) return null
  const tier = r.plan.price_tiers.find((t) => t.label === d.tier_label)
  return {
    regular: money(r.regular_reference_price_cad),
    applicable: money(d.tier_amount_cad),
    tierPhrase: tierConditionPhrase(d.tier_label, tier?.conditions ?? []),
    dollarSavings: money(d.dollar_savings_cad),
    percentSavings: `${Math.round(d.percent_savings * 100)}%`,
    conditions: tier?.conditions ?? [],
  }
}
