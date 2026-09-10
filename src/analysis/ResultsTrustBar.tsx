import type { RankingResponse } from '../api/types'
import { V1_NETWORK_FAMILY_COUNT, V1_PROVIDER_COUNT } from './providers'

interface Props {
  data: RankingResponse
  onExplain: () => void
}

function formatDay(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

/** Oldest plan-level verification date across the shown results. */
function oldestVerified(data: RankingResponse): string | null {
  const dates = data.results
    .map((r) => r.plan.last_verified_at)
    .filter((s): s is string => !!s)
  if (!dates.length) return null
  return dates.reduce((a, b) => (new Date(a) <= new Date(b) ? a : b))
}

/**
 * A compact, restrained trust / freshness strip shown just under the results
 * heading. No "real-time" / "guaranteed" / "100% accurate" language.
 */
export function ResultsTrustBar({ data, onExplain }: Props) {
  const eligible = data.pre_filter_candidate_count
  const verified = oldestVerified(data)

  return (
    <div className="rank-trust">
      <p className="rank-trust__line">
        <span className="rank-trust__dot" aria-hidden />
        <span className="rank-trust__strong">Current verified data</span>
        <span className="rank-trust__sep">·</span>
        <span>Verified from official carrier sources</span>
        {verified && (
          <>
            <span className="rank-trust__sep">·</span>
            <span>Last verified {formatDay(verified)}</span>
          </>
        )}
      </p>
      <p className="rank-trust__line rank-trust__line--muted">
        <span>
          {eligible} plan{eligible === 1 ? '' : 's'} currently eligible for
          ranking
        </span>
        <span className="rank-trust__sep">·</span>
        <span>{V1_PROVIDER_COUNT} providers</span>
        <span className="rank-trust__sep">·</span>
        <span>{V1_NETWORK_FAMILY_COUNT} network families</span>
        <button type="button" className="rank-trust__explain" onClick={onExplain}>
          How rankings work
        </button>
      </p>
    </div>
  )
}
