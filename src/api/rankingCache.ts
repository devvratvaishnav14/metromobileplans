/**
 * A tiny in-memory cache + in-flight de-duplicator for `GET /api/rank`.
 *
 * Why it exists: the map app warms the "Best Overall" ranking in the background
 * while the user is still on the miniature map, so that by the time the
 * cinematic zoom finishes and AnalysisView mounts, the data is already here and
 * renders with no loading state — without ever issuing the request twice.
 *
 * The cache key deliberately omits the municipality. For V1 the ranking is
 * identical for every supported municipality (the backend reports
 * `municipality_affects_results: false`), so the warmed default ranking is the
 * same object AnalysisView needs for Vancouver / Burnaby / Surrey. The selected
 * municipality is still sent on the wire and shown as context — no data is
 * faked or relabelled. If the backend ever makes the ranking municipality-
 * dependent, add it back to `rankingKey`.
 */
import { fetchRanking, type RankingParams } from './client'
import type { RankingResponse } from './types'

interface Entry {
  promise: Promise<RankingResponse>
  value?: RankingResponse
  at: number
}

/** How long a resolved ranking may be reused before a fresh fetch. */
const TTL_MS = 5 * 60 * 1000

const cache = new Map<string, Entry>()

/** Stable cache key for the params that actually change the response. */
export function rankingKey(p: RankingParams): string {
  const c = p.customization ?? {}
  return JSON.stringify([
    p.preset,
    Boolean(p.studentEligible),
    c.max_monthly_price_cad ?? null,
    c.min_data_gb ?? null,
    c.plan_type && c.plan_type !== 'any' ? c.plan_type : null,
    Boolean(c.require_5g),
    Boolean(c.require_can_us_mex),
    Boolean(c.require_international_roaming),
    // autopay_willing defaults to true server-side, so an omitted value (the
    // map's prefetch) and an explicit `true` (AnalysisView's initial state)
    // must hash to the same key — only an explicit opt-out (`false`) differs.
    c.autopay_willing !== false,
  ])
}

function isFresh(entry: Entry): boolean {
  return entry.value !== undefined && Date.now() - entry.at < TTL_MS
}

/** Synchronous peek — a resolved, still-fresh response for these params, if any. */
export function peekRanking(p: RankingParams): RankingResponse | undefined {
  const entry = cache.get(rankingKey(p))
  return entry && isFresh(entry) ? entry.value : undefined
}

/**
 * Resolve a ranking, sharing an in-flight request or a fresh cached value for
 * the same key. `signal` only detaches *this* caller (e.g. a component
 * unmounting mid-zoom) — it never aborts the shared fetch, so the warmed
 * request is not wasted.
 */
export function getRanking(
  p: RankingParams,
  signal?: AbortSignal,
): Promise<RankingResponse> {
  const key = rankingKey(p)
  let entry = cache.get(key)

  if (!entry || (entry.value !== undefined && !isFresh(entry))) {
    const created: Entry = { at: Date.now(), promise: undefined as never }
    created.promise = fetchRanking(p).then(
      (value) => {
        created.value = value
        created.at = Date.now()
        return value
      },
      (err) => {
        // Drop a failed entry so the next attempt re-fetches rather than
        // replaying the rejection.
        if (cache.get(key) === created) cache.delete(key)
        throw err
      },
    )
    cache.set(key, created)
    entry = created
  }

  const shared = entry.promise
  if (!signal) return shared

  return new Promise<RankingResponse>((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('Aborted', 'AbortError'))
      return
    }
    const onAbort = () => reject(new DOMException('Aborted', 'AbortError'))
    signal.addEventListener('abort', onAbort, { once: true })
    shared.then(
      (value) => {
        signal.removeEventListener('abort', onAbort)
        resolve(value)
      },
      (err) => {
        signal.removeEventListener('abort', onAbort)
        reject(err)
      },
    )
  })
}

/** Fire-and-forget warm-up. Errors are swallowed — the real request retries. */
export function prefetchRanking(p: RankingParams): void {
  getRanking(p).catch(() => {})
}

/**
 * The ranking AnalysisView shows first: Best Overall, no filters, not a
 * confirmed student. Used by the map to warm exactly what the results screen
 * will request. `customization` is omitted (equivalent to all-default) so this
 * shares a cache key and a wire request with AnalysisView's opening `useRanking`
 * call.
 */
export function defaultRankingParams(municipalityId: string | null): RankingParams {
  return { preset: 'overall', municipalityId, studentEligible: false }
}
