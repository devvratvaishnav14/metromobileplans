/**
 * The single shared customization state for the results page.
 *
 * This only *collects* user choices and turns them into `/api/rank` query
 * parameters. Every filter decision is made by the backend — nothing here
 * ranks, scores, or decides plan eligibility.
 */
import type { RankingCustomization } from '../api/types'

export type PlanTypeChoice = 'any' | 'prepaid' | 'postpaid'

export interface Customization {
  /** Maximum monthly (or monthly-equivalent) price in CAD; null = no limit. */
  maxMonthlyPriceCad: number | null
  /** Minimum domestic full-speed data in GB; null = no minimum. */
  minDataGb: number | null
  planType: PlanTypeChoice
  require5g: boolean
  requireCanUsMex: boolean
  requireInternationalRoaming: boolean
  /** Confirmed user context — never inferred from the selected preset. */
  studentEligible: boolean
  /** Default true: broadly-available AutoPay / Digital Discount pricing is
   *  used unless the user explicitly opts out to see regular prices only. */
  autopayWilling: boolean
}

export const EMPTY_CUSTOMIZATION: Customization = {
  maxMonthlyPriceCad: null,
  minDataGb: null,
  planType: 'any',
  require5g: false,
  requireCanUsMex: false,
  requireInternationalRoaming: false,
  studentEligible: false,
  autopayWilling: true,
}

/** Quick-choice values offered in the panel (plus "Any" and "Custom"). */
export const BUDGET_CHOICES = [25, 40, 50, 60] as const
export const DATA_CHOICES = [1, 10, 25, 50, 100] as const

export function customizationIsActive(c: Customization): boolean {
  return (
    c.maxMonthlyPriceCad != null ||
    c.minDataGb != null ||
    c.planType !== 'any' ||
    c.require5g ||
    c.requireCanUsMex ||
    c.requireInternationalRoaming ||
    c.studentEligible ||
    // autopayWilling defaults true — only opting OUT is a customization.
    !c.autopayWilling
  )
}

export function customizationEquals(a: Customization, b: Customization): boolean {
  return (
    a.maxMonthlyPriceCad === b.maxMonthlyPriceCad &&
    a.minDataGb === b.minDataGb &&
    a.planType === b.planType &&
    a.require5g === b.require5g &&
    a.requireCanUsMex === b.requireCanUsMex &&
    a.requireInternationalRoaming === b.requireInternationalRoaming &&
    a.studentEligible === b.studentEligible &&
    a.autopayWilling === b.autopayWilling
  )
}

/** Stable string for a fetch key — order matters, keep it deterministic. */
export function customizationKey(c: Customization): string {
  return [
    c.maxMonthlyPriceCad ?? '',
    c.minDataGb ?? '',
    c.planType,
    c.require5g ? 1 : 0,
    c.requireCanUsMex ? 1 : 0,
    c.requireInternationalRoaming ? 1 : 0,
    c.studentEligible ? 1 : 0,
    c.autopayWilling ? 1 : 0,
  ].join('|')
}

/** Map the UI state to the API's snake_case customization inputs.
 *  `student_eligible` is sent separately via the explicit arg in the client. */
export function toRankingCustomization(c: Customization): RankingCustomization {
  return {
    max_monthly_price_cad: c.maxMonthlyPriceCad,
    min_data_gb: c.minDataGb,
    plan_type: c.planType,
    require_5g: c.require5g,
    require_can_us_mex: c.requireCanUsMex,
    require_international_roaming: c.requireInternationalRoaming,
    autopay_willing: c.autopayWilling,
  }
}

export interface CustomizationChip {
  /** Which field this chip represents — used to remove just this one. */
  key: keyof Customization
  label: string
}

/** Compact chips for the active-filter summary. Inactive/default filters are
 *  never included. */
export function customizationChips(c: Customization): CustomizationChip[] {
  const chips: CustomizationChip[] = []
  if (c.maxMonthlyPriceCad != null)
    chips.push({ key: 'maxMonthlyPriceCad', label: `≤ $${c.maxMonthlyPriceCad}/mo` })
  if (c.minDataGb != null)
    chips.push({ key: 'minDataGb', label: `${c.minDataGb} GB+` })
  if (c.planType !== 'any')
    chips.push({
      key: 'planType',
      label: c.planType === 'prepaid' ? 'Prepaid' : 'Postpaid',
    })
  if (c.require5g) chips.push({ key: 'require5g', label: '5G' })
  if (c.requireCanUsMex)
    chips.push({ key: 'requireCanUsMex', label: 'Canada-US-Mexico' })
  if (c.requireInternationalRoaming)
    chips.push({ key: 'requireInternationalRoaming', label: 'International roaming' })
  if (c.studentEligible)
    chips.push({ key: 'studentEligible', label: 'Student eligible' })
  // autopayWilling defaults true; the chip represents the non-default,
  // opted-out state, matching how every other chip only appears when it
  // changes the result from the default ranking.
  if (!c.autopayWilling)
    chips.push({ key: 'autopayWilling', label: 'Regular price only' })
  return chips
}

/** Return a copy with one chip's filter cleared back to its default. */
export function clearCustomizationField(
  c: Customization,
  key: keyof Customization,
): Customization {
  switch (key) {
    case 'maxMonthlyPriceCad':
      return { ...c, maxMonthlyPriceCad: null }
    case 'minDataGb':
      return { ...c, minDataGb: null }
    case 'planType':
      return { ...c, planType: 'any' }
    case 'autopayWilling':
      // Its chip only appears when opted out (false) — clearing it restores
      // the default (true), not false like the other boolean toggles.
      return { ...c, autopayWilling: true }
    default:
      return { ...c, [key]: false }
  }
}
