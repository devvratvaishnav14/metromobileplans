/**
 * Shapes returned by the metro-mobile-plans backend (`backend/metromobile`).
 * Kept in sync by hand with `backend/metromobile/schemas.py`.
 */

export type Freshness = 'fresh' | 'aging' | 'stale'

export type SourceMode =
  | 'official_automated'
  | 'official_manual'
  | 'trusted_secondary'

export interface ProviderMeta {
  slug: string
  display_name: string
  network: string | null
  plan_model: string | null
  default_source_mode: SourceMode | null
  source_url: string
  source_kind: string
}

export interface PlanIssue {
  severity: 'error' | 'warning'
  field: string | null
  message: string
}

export interface Plan {
  id: number
  provider_slug: string
  provider_name: string
  external_id: string
  plan_name: string | null
  plan_local_name: string | null

  // pricing tiers (direct from the record)
  price_cad: number | null
  price_period: 'monthly' | 'annual' | null
  term_months: number | null
  monthly_price_cad: number | null
  regular_price_cad: number | null       // unconditional
  autopay_price_cad: number | null
  autopay_discount_cad: number | null
  autopay_conditions: string | null
  bundle_price_cad: number | null        // requires home-internet / streaming bundle
  bundle_discount_cad: number | null
  bundle_conditions: string | null
  promo_price_cad: number | null
  promo_conditions: string | null
  promo_stacks_conditions: string | null
  pricing_notes: Array<{ amount: number; label: string }> | null

  // pricing (computed at serve time)
  universal_price_cad: number | null     // what a neutral ranking uses
  display_price_cad: number | null       // shown by default (never a conditional price)
  best_case_price_cad: number | null     // lowest with all conditions + active promo
  price_tiers: Array<{ amount: number; label: string; conditions: string[] }>
  has_conditional_discounts: boolean
  price_note: string | null
  offer_is_conditional: boolean

  // promotion (structured)
  promo_name: string | null
  promo_savings_cad: number | null
  promo_starts_at: string | null
  promo_ends_at: string | null
  promo_expiry_known: boolean | null
  promo_duration_months: number | null
  promo_new_customers_only: boolean | null
  promo_online_only: boolean | null
  promo_autopay_required: boolean | null
  promo_source_url: string | null

  // computed current-offer state (serve time)
  effective_price_cad: number | null
  is_current_offer: boolean
  offer_active: boolean
  offer_expired: boolean
  offer_savings_cad: number | null
  offer_note: string | null

  // fees / contract / device
  activation_fee_cad: number | null
  activation_fee_waived: boolean | null
  activation_note: string | null
  contract_required: boolean | null
  contract_length_months: number | null
  contract_note: string | null
  byod: boolean | null
  byod_required: boolean | null
  device_restrictions: string | null

  // data
  data_base_gb: number | null
  data_bonus_gb: number | null
  data_promo_gb: number | null
  data_total_gb: number | null
  data_full_speed_gb: number | null
  data_unlimited: boolean | null
  data_unlimited_is_full_speed: boolean | null
  data_hard_cap: boolean | null
  throttled_after_note: string | null
  throttle_speed: string | null
  overage_note: string | null
  overage_rate_per_gb_cad: number | null
  data_rollover: boolean | null

  // network
  network_speed_tier: string | null
  network_technology: string | null
  max_download_mbps: number | null
  has_5g: boolean | null

  // calling / travel
  plan_type: string | null
  canada_wide_calling: boolean | null
  unlimited_text: boolean | null
  international_text: boolean | null
  can_us_mex_note: string | null
  includes_us: boolean | null
  includes_mexico: boolean | null
  us_mex_data_gb: number | null
  international_roaming: boolean | null
  international_roaming_note: string | null

  // features
  hotspot: boolean | null
  hotspot_data_gb: number | null
  hotspot_note: string | null
  esim: boolean | null
  wifi_calling: boolean | null
  autopay_required: boolean | null
  autopay_note: string | null

  // student
  student_plan: boolean | null
  student_offer: boolean | null
  student_eligibility_note: string | null

  // restricted eligibility (partner / employer / exclusive offer)
  eligibility_restricted: boolean | null
  eligibility_conditions: string | null

  // geography
  available_regions: string[] | null
  geo_availability_note: string | null

  conditions: string | null
  availability: string | null

  attributes: Record<string, unknown>

  source_mode: SourceMode
  source_mode_label: string
  verification_method: string
  verified_by: string | null
  official_crosscheck: boolean
  source_url: string
  fetched_at: string
  last_verified_at: string
  first_verified_at: string
  verification_status: string
  stored_verification_status: string
  confidence: number
  is_rankable: boolean
  freshness: Freshness
  freshness_label: string
  verification_event_count: number

  issues: PlanIssue[]
}

export interface AnalysisMeta {
  municipality: string | null
  municipality_affects_results: boolean
  generated_at: string
  data_last_refreshed_at: string | null
  data_oldest_verified_at: string | null
  freshness: Freshness | null
  freshness_label: string
  plan_count: number
  current_plan_count: number
  rankable_count: number
  current_offer_count: number
  flagged_count: number
  provider_count: number
  source_mode_counts: Record<string, number>
  providers: ProviderMeta[]
  notes: string[]
}

export interface PlansResponse {
  meta: AnalysisMeta
  plans: Plan[]
  scores: unknown[]
  profiles: unknown[]
}

/* --------------------------------------------------------------------------
   Ranking API (`GET /api/rank`). The backend is the single source of truth
   for every score below — the frontend never recomputes any of this.
   Kept in sync by hand with `backend/metromobile/schemas.py`.
   ------------------------------------------------------------------------ */

export type RankingPreset =
  | 'overall'
  | 'students'
  | 'cheapest'
  | 'most_data'
  | 'offers'

/** One conditional pricing tier evaluated by the Offer component, against the
 *  plan's fixed unconditional regular reference price. */
export interface OfferDetail {
  tier_label: string
  tier_amount_cad: number
  dollar_savings_cad: number
  percent_savings: number // 0..1
  percent_score: number // 0..100
  dollar_score: number // 0..100
  base_offer_score: number // 0..100
  condition_ease: number // internal multiplier — not shown on the normal card
  expiry_ease: number // internal multiplier — not shown on the normal card
  duration_bonus: number
  offer_score: number // 0..100, the final Offer component value for this plan
}

/** Upfront-payment / term facts for an annually-billed plan (e.g. Chatr's
 *  $159 / 12 months). Never used to infer a contract or lock-in. */
export interface Commitment {
  upfront_cad: number
  term_months: number
}

export interface RankedPlan {
  rank: number
  plan_id: number
  provider_slug: string
  provider_name: string
  external_id: string
  plan_name: string | null

  /** The full factual plan record (same shape as `/api/plans`). Used only to
   *  explain the ranking and disclose conditional pricing — never re-scored. */
  plan: Plan

  final_score: number // 0..100
  price_score: number | null
  data_score: number | null
  technology_score: number | null
  features_score: number | null
  roaming_score: number | null
  offer_score: number | null

  /** The monthly price actually used for THIS user's ranking (may be a verified
   *  student / AutoPay price once eligibility is confirmed). */
  price_used_cad: number | null
  /** The fixed, unconditional regular reference price — what the Offer component
   *  always measures savings against, even after eligibility is confirmed. */
  regular_reference_price_cad: number | null
  /** Which tier `price_used_cad` came from, if not the regular price. */
  applicable_tier_label: string | null
  /** Period-normalized monthly-equivalent price (annual total ÷ term_months). */
  monthly_equivalent_price_cad: number | null
  commitment: Commitment | null
  offer_detail: OfferDetail | null
  eligibility_note: string | null
  /** Short, deterministic, template-generated explanation lines (not from an LLM). */
  reasons: string[]
}

export type PlanTypeFilter = 'prepaid' | 'postpaid'

/** Optional V1 customization inputs. All omitted / falsey = no change to the
 *  ranking. These only filter the candidate pool + set confirmed user context;
 *  they never alter a preset's scoring formula. */
export interface RankingCustomization {
  max_monthly_price_cad?: number | null
  min_data_gb?: number | null
  /** 'any' is sent as no filter. */
  plan_type?: PlanTypeFilter | 'any' | null
  require_5g?: boolean
  require_can_us_mex?: boolean
  require_international_roaming?: boolean
  student_eligible?: boolean
  autopay_willing?: boolean
}

/** Factual, normalized description of the customization the backend applied —
 *  for explaining the list (and the empty state). No scoring logic. */
export interface FiltersApplied {
  max_monthly_price_cad: number | null
  min_data_gb: number | null
  plan_type: PlanTypeFilter | null
  require_5g: boolean
  require_can_us_mex: boolean
  require_international_roaming: boolean
  student_eligible: boolean
  autopay_willing: boolean
  /** true when at least one hard filter narrowed the candidate pool. */
  any_active: boolean
}

export interface RankingResponse {
  preset: RankingPreset
  municipality: string | null
  municipality_affects_results: boolean
  student_eligible: boolean
  autopay_willing: boolean
  generated_at: string
  /** plans that passed every filter and were scored (before the Top-N cut). */
  candidate_count: number
  /** plans after verified/eligibility gating, before the custom hard filters. */
  pre_filter_candidate_count: number
  filters_applied: FiltersApplied
  results: RankedPlan[]
}
