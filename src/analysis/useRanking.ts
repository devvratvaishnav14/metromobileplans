import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import type { RankingParams } from '../api/client'
import { getRanking, peekRanking } from '../api/rankingCache'
import type { RankingPreset, RankingResponse } from '../api/types'
import {
  customizationKey,
  toRankingCustomization,
  type Customization,
} from './customization'

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: RankingResponse; refreshing: boolean }

interface Resolved {
  key: string
  state:
    | { status: 'error'; message: string }
    | { status: 'ready'; data: RankingResponse }
}

interface Args {
  preset: RankingPreset
  municipalityId: string | null
  /** The committed customization (draft edits do not reach here until Apply). */
  customization: Customization
}

/**
 * Loads a ranked Top-N from `GET /api/rank` for the current preset / municipality
 * / committed customization. Every score and every filter decision comes from
 * the backend — nothing is ranked, re-weighted, or filtered here.
 *
 * While a change is fetching, the previously loaded results stay on screen
 * (`refreshing: true`) so switching presets or applying filters doesn't collapse
 * the layout. A fetch error is always shown — results are never silently served
 * from a stale response.
 */
export function useRanking({
  preset,
  municipalityId,
  customization,
}: Args): State & { reload: () => void } {
  const [nonce, setNonce] = useState(0)
  const key = `${preset}#${municipalityId ?? ''}#${customizationKey(customization)}#${nonce}`

  const params: RankingParams = {
    preset,
    municipalityId,
    // student eligibility is a confirmed user-context flag; it applies to
    // every preset once set, not only "Best for Students".
    studentEligible: customization.studentEligible,
    customization: toRankingCustomization(customization),
  }

  const [resolved, setResolved] = useState<Resolved | null>(null)

  useEffect(() => {
    const ctrl = new AbortController()
    // `getRanking` returns a warm cache hit or a shared in-flight request when
    // one exists (the map prefetches "Best Overall" before this ever mounts),
    // so the normal map -> results journey never issues a second request.
    getRanking(params, ctrl.signal)
      .then((data) => setResolved({ key, state: { status: 'ready', data } }))
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return
        const message =
          err instanceof ApiError
            ? err.message
            : 'Unexpected error loading the ranking.'
        setResolved({ key, state: { status: 'error', message } })
      })
    return () => ctrl.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  // A ranking already warmed for these params (prefetched during the zoom, or a
  // preset visited earlier) is rendered straight away — derived here rather than
  // set in the effect, so there is no loading flash and no extra render.
  const warm = resolved?.key === key ? undefined : peekRanking(params)

  let state: State
  if (resolved?.key === key) {
    state =
      resolved.state.status === 'ready'
        ? { status: 'ready', data: resolved.state.data, refreshing: false }
        : resolved.state
  } else if (warm) {
    state = { status: 'ready', data: warm, refreshing: false }
  } else if (resolved?.state.status === 'ready') {
    // a newer request is in flight — keep the last results visible, dimmed
    state = { status: 'ready', data: resolved.state.data, refreshing: true }
  } else {
    state = { status: 'loading' }
  }

  return { ...state, reload: () => setNonce((n) => n + 1) }
}
