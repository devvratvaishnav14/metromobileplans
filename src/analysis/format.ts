import type { Plan } from '../api/types'

function money(n: number): string {
  return `$${Number.isInteger(n) ? n : n.toFixed(2)}`
}

function unitFor(plan: Plan): string {
  if (plan.price_period === 'annual') return plan.term_months ? `/ ${plan.term_months} mo` : '/ yr'
  if (plan.price_period === 'monthly') return '/ mo'
  return ''
}

/**
 * What a customer pays now. Never a conditional (bundle / AutoPay) price presented
 * as if universal: `effective_price_cad` is the unconditional price with an active
 * non-conditional promo applied; `display_price_cad` is the conservative fallback
 * when only conditional prices are known.
 */
export function priceLabel(plan: Plan): { amount: string; unit: string } | null {
  const value = plan.effective_price_cad ?? plan.display_price_cad ?? plan.price_cad
  if (value == null) return null
  return { amount: money(value), unit: unitFor(plan) }
}

/** The struck-through "was" price, only when a current offer beats it. */
export function wasPriceLabel(plan: Plan): string | null {
  if (!plan.is_current_offer) return null
  const regular =
    plan.universal_price_cad ?? plan.regular_price_cad ?? plan.monthly_price_cad
  if (regular == null || regular === plan.effective_price_cad) return null
  return money(regular)
}

/** Short note when the shown price is conditional or the unconditional one is unknown. */
export function priceCaveat(plan: Plan): string | null {
  if (plan.price_note) return plan.price_note
  if (plan.universal_price_cad == null && plan.has_conditional_discounts) {
    return 'Only conditional pricing is on record — not yet rankable'
  }
  if (plan.has_conditional_discounts && plan.best_case_price_cad != null) {
    return `As low as ${money(plan.best_case_price_cad)}/mo with bundle / AutoPay / promo`
  }
  return null
}

export function dataLabel(plan: Plan): string {
  const cap =
    plan.data_full_speed_gb ?? plan.data_total_gb ?? plan.data_base_gb
  if (plan.data_unlimited) {
    if (cap != null && plan.data_unlimited_is_full_speed === false) {
      const after = plan.throttle_speed ? `unlimited at ${plan.throttle_speed}` : 'unlimited (slower)'
      return `${trimGb(cap)} GB at full speed, then ${after}`
    }
    return 'Unlimited data'
  }
  if (plan.data_total_gb != null) {
    const total = trimGb(plan.data_total_gb)
    if (plan.data_bonus_gb && plan.data_base_gb != null) {
      return `${total} GB (${trimGb(plan.data_base_gb)} GB + ${trimGb(plan.data_bonus_gb)} GB autopay bonus)`
    }
    return `${total} GB`
  }
  if (plan.data_bonus_gb != null) return `${trimGb(plan.data_bonus_gb)} GB autopay bonus`
  return 'No data — talk & text'
}

function trimGb(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1)
}

export function ternaryLabel(
  value: boolean | null,
  yes: string,
  no: string | null,
): string | null {
  if (value === true) return yes
  if (value === false) return no
  return null
}

function isoDate(s: string | null): string | null {
  if (!s) return null
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? s : d.toLocaleDateString()
}

/** Every non-null normalized field, as [label, value] rows for the detail view. */
export function detailRows(plan: Plan): Array<[string, string]> {
  const rows: Array<[string, string | null]> = [
    ['Provider', plan.provider_name],
    ['Plan name', plan.plan_name],
    ['Plan type', plan.plan_type],
    ['You pay now', plan.effective_price_cad != null ? `${money(plan.effective_price_cad)} ${unitFor(plan)}`.trim() : plan.display_price_cad != null ? `${money(plan.display_price_cad)} ${unitFor(plan)}`.trim() : null],
    ['Regular price (unconditional)', plan.regular_price_cad != null ? money(plan.regular_price_cad) : null],
    ['Price with AutoPay', plan.autopay_price_cad != null ? money(plan.autopay_price_cad) : null],
    ['AutoPay conditions', plan.autopay_conditions],
    ['Price with bundle', plan.bundle_price_cad != null ? money(plan.bundle_price_cad) : null],
    ['Bundle conditions', plan.bundle_conditions],
    ['Universal (rankable) price', plan.universal_price_cad != null ? money(plan.universal_price_cad) : null],
    ['Best-case price', plan.best_case_price_cad != null && plan.best_case_price_cad !== plan.universal_price_cad ? money(plan.best_case_price_cad) : null],
    ['Pricing note', priceCaveat(plan)],
    ['Promotional price', plan.promo_price_cad != null ? money(plan.promo_price_cad) : null],
    ['Promo also requires', plan.promo_stacks_conditions],
    ['Offer savings', plan.offer_savings_cad != null ? money(plan.offer_savings_cad) : null],
    ['Offer name', plan.promo_name],
    ['Offer starts', isoDate(plan.promo_starts_at)],
    ['Offer ends', isoDate(plan.promo_ends_at)],
    ['Offer expiry known', ternaryLabel(plan.promo_expiry_known, 'Yes', 'No — time-limited, no date')],
    ['Offer status', plan.offer_expired ? 'Expired' : plan.is_current_offer ? 'Current offer' : plan.promo_price_cad != null ? 'Not currently better than regular' : null],
    ['Offer: new customers only', ternaryLabel(plan.promo_new_customers_only, 'Yes', 'No')],
    ['Offer: online only', ternaryLabel(plan.promo_online_only, 'Yes', 'No')],
    ['Offer: autopay required', ternaryLabel(plan.promo_autopay_required, 'Yes', 'No')],
    ['Promo duration', plan.promo_duration_months != null ? `${plan.promo_duration_months} months` : null],
    ['Promo conditions', plan.promo_conditions],
    ['Term', plan.term_months != null ? `${plan.term_months} months` : null],
    ['Contract required', ternaryLabel(plan.contract_required, `Yes${plan.contract_length_months ? ` (${plan.contract_length_months} mo)` : ''}`, 'No')],
    ['Contract note', plan.contract_note],
    ['BYOD', ternaryLabel(plan.byod, 'Yes', 'No')],
    ['BYOD required', ternaryLabel(plan.byod_required, 'Yes', 'No')],
    ['Device restrictions', plan.device_restrictions],
    ['Activation fee', plan.activation_fee_waived ? 'None' : plan.activation_fee_cad != null ? money(plan.activation_fee_cad) : null],
    ['Base data', plan.data_base_gb != null ? `${plan.data_base_gb} GB` : null],
    ['Bonus / autopay data', plan.data_bonus_gb != null ? `${plan.data_bonus_gb} GB` : null],
    ['Promotional data', plan.data_promo_gb != null ? `${plan.data_promo_gb} GB` : null],
    ['Total data', plan.data_total_gb != null ? `${plan.data_total_gb} GB` : null],
    ['Full-speed data', plan.data_full_speed_gb != null ? `${plan.data_full_speed_gb} GB` : null],
    ['Unlimited data', ternaryLabel(plan.data_unlimited, plan.data_unlimited_is_full_speed === false ? 'Yes (slower after cap)' : 'Yes', 'No')],
    ['Hard data cap', ternaryLabel(plan.data_hard_cap, 'Yes', 'No')],
    ['After data used up', plan.throttled_after_note],
    ['Throttle speed', plan.throttle_speed],
    ['Overage', plan.overage_rate_per_gb_cad != null ? `${money(plan.overage_rate_per_gb_cad)} / GB` : plan.overage_note],
    ['Data rollover', ternaryLabel(plan.data_rollover, 'Yes', 'No')],
    ['Network', plan.network_technology],
    ['Advertised speed', plan.network_speed_tier ?? (plan.max_download_mbps != null ? `up to ${plan.max_download_mbps} Mbps` : null)],
    ['5G', ternaryLabel(plan.has_5g, 'Yes', 'No (4G)')],
    ['Canada-wide calling', ternaryLabel(plan.canada_wide_calling, 'Unlimited', 'Limited / metered')],
    ['Text', ternaryLabel(plan.unlimited_text, 'Unlimited', null)],
    ['International text', ternaryLabel(plan.international_text, 'Included', null)],
    ['US usage included', ternaryLabel(plan.includes_us, 'Yes', 'No')],
    ['Mexico usage included', ternaryLabel(plan.includes_mexico, 'Yes', 'No')],
    ['Canada / US / Mexico data', plan.us_mex_data_gb != null ? `${plan.us_mex_data_gb} GB` : null],
    ['Canada / US / intl note', plan.can_us_mex_note],
    ['International roaming', ternaryLabel(plan.international_roaming, 'Available', 'Not included') ?? plan.international_roaming_note],
    ['Hotspot / tethering', ternaryLabel(plan.hotspot, plan.hotspot_data_gb != null ? `Yes (${plan.hotspot_data_gb} GB)` : 'Yes', 'No') ?? plan.hotspot_note],
    ['eSIM', ternaryLabel(plan.esim, 'Yes', 'No')],
    ['Wi-Fi calling', ternaryLabel(plan.wifi_calling, 'Yes', 'No')],
    ['Autopay required', ternaryLabel(plan.autopay_required, 'Yes', 'No')],
    ['Autopay note', plan.autopay_note],
    ['Student plan', ternaryLabel(plan.student_plan, 'Yes', null)],
    ['Student offer', ternaryLabel(plan.student_offer, 'Yes', null)],
    ['Student eligibility', plan.student_eligibility_note],
    ['Restricted offer', ternaryLabel(plan.eligibility_restricted, 'Yes — not for ordinary customers', null)],
    ['Eligibility condition', plan.eligibility_conditions],
    ['Available regions', plan.available_regions?.length ? plan.available_regions.join(', ') : null],
    ['Geographic availability', plan.geo_availability_note],
    ['Included services', plan.conditions],
    ['Availability', plan.availability],
    ['Source mode', plan.source_mode_label],
    ['Verification method', plan.verification_method.replace(/_/g, ' ')],
    ['Verified by', plan.verified_by],
    ['Official cross-check', plan.official_crosscheck ? 'Yes' : null],
    ['Verification status', plan.verification_status],
    ['Verification checks on record', String(plan.verification_event_count)],
    ['Confidence', `${Math.round(plan.confidence * 100)}%`],
  ]
  return rows.filter((r): r is [string, string] => r[1] != null && r[1] !== '')
}
