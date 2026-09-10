import type {
  PlansResponse,
  RankingCustomization,
  RankingPreset,
  RankingResponse,
} from './types'

/**
 * Base URL of the metro-mobile-plans backend. Override with VITE_API_BASE_URL
 * (see `.env.example`); defaults to the local dev server.
 */
const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
).replace(/\/$/, '')

export class ApiError extends Error {
  constructor(message: string, options?: { cause?: unknown }) {
    super(message, options)
    this.name = 'ApiError'
  }
}

export async function fetchPlans(
  municipalityId: string | null,
  signal?: AbortSignal,
): Promise<PlansResponse> {
  const url = new URL(`${API_BASE_URL}/api/plans`)
  if (municipalityId) url.searchParams.set('municipality', municipalityId)

  let res: Response
  try {
    res = await fetch(url, { signal, headers: { Accept: 'application/json' } })
  } catch (err) {
    throw new ApiError(
      `Could not reach the plan-analysis backend at ${API_BASE_URL}. Is it running?`,
      { cause: err },
    )
  }
  if (!res.ok) {
    throw new ApiError(`Backend responded ${res.status} ${res.statusText}`)
  }
  return (await res.json()) as PlansResponse
}

export interface RankingParams {
  preset: RankingPreset
  municipalityId: string | null
  /** Only ever true after the user explicitly confirms eligibility. */
  studentEligible?: boolean
  /** Optional V1 hard filters + confirmed context. Omit for the default ranking. */
  customization?: RankingCustomization
}

/**
 * Fetch a ranked Top-N from the backend ranking engine. All scoring happens
 * server-side; the response is the single source of truth. Customization only
 * filters the candidate pool — it never changes a preset's scoring.
 */
export async function fetchRanking(
  { preset, municipalityId, studentEligible = false, customization }: RankingParams,
  signal?: AbortSignal,
): Promise<RankingResponse> {
  const url = new URL(`${API_BASE_URL}/api/rank`)
  url.searchParams.set('preset', preset)
  if (municipalityId) url.searchParams.set('municipality', municipalityId)
  if (studentEligible) url.searchParams.set('student_eligible', 'true')

  const c = customization ?? {}
  if (c.max_monthly_price_cad != null)
    url.searchParams.set('max_monthly_price_cad', String(c.max_monthly_price_cad))
  if (c.min_data_gb != null) url.searchParams.set('min_data_gb', String(c.min_data_gb))
  if (c.plan_type && c.plan_type !== 'any') url.searchParams.set('plan_type', c.plan_type)
  if (c.require_5g) url.searchParams.set('require_5g', 'true')
  if (c.require_can_us_mex) url.searchParams.set('require_can_us_mex', 'true')
  if (c.require_international_roaming)
    url.searchParams.set('require_international_roaming', 'true')
  if (c.autopay_willing) url.searchParams.set('autopay_willing', 'true')
  // `student_eligible` stays driven by the explicit `studentEligible` arg above.

  let res: Response
  try {
    res = await fetch(url, { signal, headers: { Accept: 'application/json' } })
  } catch (err) {
    throw new ApiError(
      `Could not reach the ranking backend at ${API_BASE_URL}. Is it running?`,
      { cause: err },
    )
  }
  if (!res.ok) {
    throw new ApiError(`Ranking API responded ${res.status} ${res.statusText}`)
  }
  return (await res.json()) as RankingResponse
}
