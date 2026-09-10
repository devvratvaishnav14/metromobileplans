/**
 * V1 plan-analysis coverage.
 *
 * The whole Metro Vancouver miniature world stays rendered as scenery, but only
 * these municipalities are interactive — hover name, highlight, click → the
 * character walk → confirm → cinematic zoom → AnalysisView. Every other
 * municipality is inert (no hover, no glow, no click).
 *
 * This is the ONE place the supported set is defined. To unlock another
 * municipality later, add its id here — nothing else needs to change.
 */
export const SUPPORTED_MUNICIPALITY_IDS = ['vancouver', 'burnaby', 'surrey'] as const

export type SupportedMunicipalityId = (typeof SUPPORTED_MUNICIPALITY_IDS)[number]

const SUPPORTED_SET: ReadonlySet<string> = new Set(SUPPORTED_MUNICIPALITY_IDS)

/** True when a municipality id has full V1 plan analysis. */
export function isSupportedMunicipality(id: string | null | undefined): boolean {
  return id != null && SUPPORTED_SET.has(id)
}
