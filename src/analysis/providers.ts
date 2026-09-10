/**
 * Small display-only metadata for each V1 plan provider: an identifier mark and
 * the underlying radio network. Purely presentational — it does not touch
 * ranking, filtering, or the plan data itself.
 *
 * The marks are simple original brand-coloured badges, not the carriers'
 * official logo artwork. The results page carries an "independent, not
 * affiliated" disclaimer covering the use of the names and marks.
 */
import bellMark from '../assets/logos/bell.svg'
import chatrMark from '../assets/logos/chatr.svg'
import freedomMark from '../assets/logos/freedom-mobile.svg'
import koodoMark from '../assets/logos/koodo.svg'

export interface ProviderBrand {
  /** Preferred display name (falls back to the API's provider_name). */
  name: string
  /** URL of the local identifier mark. */
  mark: string
  /** Underlying network, shown as small secondary text — null when it's the
   *  same brand (e.g. Bell on Bell) and would just be noise. */
  network: string | null
}

const BRANDS: Record<string, ProviderBrand> = {
  chatr: { name: 'Chatr', mark: chatrMark, network: 'Rogers network' },
  bell: { name: 'Bell', mark: bellMark, network: null },
  koodo: { name: 'Koodo', mark: koodoMark, network: 'TELUS network' },
  'freedom-mobile': {
    name: 'Freedom Mobile',
    mark: freedomMark,
    network: 'Freedom (Videotron) network',
  },
}

export function providerBrand(slug: string): ProviderBrand | null {
  return BRANDS[slug] ?? null
}
