import { useEffect, useState } from 'react'
import { ApiError, fetchPlans } from '../api/client'
import type { PlansResponse } from '../api/types'

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: PlansResponse }

interface Resolved {
  key: string
  state: Extract<State, { status: 'error' | 'ready' }>
}

/** Loads the current plans for a municipality from the backend. */
export function useAnalysis(
  municipalityId: string | null,
): State & { reload: () => void } {
  const [nonce, setNonce] = useState(0)
  const key = `${municipalityId ?? ''}#${nonce}`
  const [resolved, setResolved] = useState<Resolved | null>(null)

  useEffect(() => {
    const ctrl = new AbortController()
    fetchPlans(municipalityId, ctrl.signal)
      .then((data) => setResolved({ key, state: { status: 'ready', data } }))
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return
        const message =
          err instanceof ApiError ? err.message : 'Unexpected error loading plan data.'
        setResolved({ key, state: { status: 'error', message } })
      })
    return () => ctrl.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const state: State = resolved?.key === key ? resolved.state : { status: 'loading' }
  return { ...state, reload: () => setNonce((n) => n + 1) }
}
