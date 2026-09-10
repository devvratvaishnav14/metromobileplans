/**
 * V1 plan-analysis coverage.
 *
 * The whole Metro Vancouver miniature map stays visible and hoverable, but only
 * these municipalities enter the full analysis flow (character walk → confirm →
 * cinematic zoom → AnalysisView → `/api/rank`). Every other municipality shows a
 * "Coverage coming soon" message instead.
 *
 * This is the ONE place the supported set is defined. To unlock another
 * municipality later, add its id here — nothing else needs to change.
 */
import { getMunicipality } from './municipalities'

export const SUPPORTED_MUNICIPALITY_IDS = ['vancouver', 'burnaby', 'surrey'] as const

export type SupportedMunicipalityId = (typeof SUPPORTED_MUNICIPALITY_IDS)[number]

const SUPPORTED_SET: ReadonlySet<string> = new Set(SUPPORTED_MUNICIPALITY_IDS)

/** True when a municipality id has full V1 plan analysis. */
export function isSupportedMunicipality(id: string | null | undefined): boolean {
  return id != null && SUPPORTED_SET.has(id)
}

/** e.g. "Vancouver, Burnaby and Surrey" — derived from the list above so it
 *  never drifts out of sync when the supported set changes. */
export function supportedMunicipalityNames(): string {
  const names = SUPPORTED_MUNICIPALITY_IDS.map(
    (id) => getMunicipality(id)?.name ?? id,
  )
  if (names.length <= 1) return names.join('')
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}
