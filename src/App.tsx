import { useEffect, useRef, useSyncExternalStore } from 'react'
import { Scene } from './scene/Scene'
import { AnalysisView } from './analysis/AnalysisView'
import { CharacterInspector } from './scene/character/CharacterInspector'
import { Overlay } from './ui/Overlay'
import { CinematicTransition } from './ui/CinematicTransition'
import { useDestinationFlow } from './flow/useDestinationFlow'
import { pingBackend } from './api/client'
import { defaultRankingParams, prefetchRanking } from './api/rankingCache'

/** Subscribe to `location.hash` so the dev inspector route reacts to changes. */
function useHash() {
  return useSyncExternalStore(
    (cb) => {
      window.addEventListener('hashchange', cb)
      return () => window.removeEventListener('hashchange', cb)
    },
    () => window.location.hash,
  )
}

/**
 * The main experience. Owns the flow state and swaps the miniature map for the
 * plan-analysis interface once the cinematic dive has run; the DOM overlays and
 * the transition wash live alongside both.
 */
function MapExperience() {
  const flow = useDestinationFlow()
  // Screen-space point the transition wash blooms from — populated by the map's
  // CinematicPushIn as the camera dives toward the selected municipality.
  const focusRef = useRef({ x: 50, y: 50 })

  // As soon as the map is up, wake the (free-tier, possibly cold) backend and
  // warm the default "Best Overall" ranking in the background. By the time the
  // user picks a city and the cinematic zoom finishes, AnalysisView reuses this
  // instead of firing its own request. Cold starts still cost what they cost —
  // this just overlaps that boot with the intro + city pick.
  useEffect(() => {
    pingBackend()
    prefetchRanking(defaultRankingParams(null))
  }, [])

  const showTransition = flow.phase === 'zooming' || flow.phase === 'results'

  return (
    <>
      {flow.showResults ? (
        <AnalysisView municipalityId={flow.destinationId} onBack={flow.restart} />
      ) : (
        <Scene
          destinationId={flow.destinationId}
          onSelect={flow.selectMunicipality}
          onArrive={flow.handleArrival}
          speechText={flow.spokenLine}
          pushIn={flow.pushingIn}
          focusRef={focusRef}
        />
      )}

      {showTransition && (
        <CinematicTransition
          stage={flow.phase === 'zooming' ? 'in' : 'out'}
          focusRef={focusRef}
        />
      )}

      {!showTransition && (
        <Overlay
          journeyStarted={flow.destinationId !== null}
          confirmation={
            flow.pendingName && flow.destinationId
              ? {
                  instanceKey: flow.destinationId,
                  placeName: flow.pendingName,
                  onConfirm: flow.confirm,
                  onReject: flow.reject,
                }
              : null
          }
        />
      )}
    </>
  )
}

function App() {
  const hash = useHash()

  // DEV-ONLY route: /#inspect-character opens the close-up character inspector.
  if (hash === '#inspect-character') {
    return <CharacterInspector />
  }

  return <MapExperience />
}

export default App
