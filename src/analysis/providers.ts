/**
 * Display-only metadata for each V1 plan provider: the preferred name, the
 * underlying radio network, and — if an official logo file has been dropped
 * into `src/assets/logos/` — its URL. Purely presentational; it does not touch
 * ranking, filtering, or the plan data.
 *
 * Logos load via `import.meta.glob`, so the app builds whether or not the files
 * are present. See `src/assets/logos/README.md`. The results page carries an
 * independent-comparison disclaimer covering the use of the names and logos.
 */
const LOGO_FILES = import.meta.glob('../assets/logos/*.{svg,png,webp,jpg,jpeg}', {
  eager: true,
  import: 'default',
  query: '?url',
}) as Record<string, string>

function logoFor(slug: string): string | null {
  for (const [path, url] of Object.entries(LOGO_FILES)) {
    const base = path.split('/').pop()?.replace(/\.[^.]+$/, '')
    if (base === slug) return url
  }
  return null
}

export interface ProviderBrand {
  /** Preferred display name (falls back to the API's provider_name). */
  name: string
  /** URL of the official logo, or null when no file has been added yet. */
  logo: string | null
  /** Underlying network, shown as small secondary text — null when it's the
   *  same brand (e.g. Bell on Bell) and would just be noise. */
  network: string | null
}

const NETWORKS: Record<string, { name: string; network: string | null }> = {
  chatr: { name: 'Chatr', network: 'Rogers network' },
  bell: { name: 'Bell', network: null },
  koodo: { name: 'Koodo', network: 'TELUS network' },
  'freedom-mobile': { name: 'Freedom Mobile', network: 'Freedom (Videotron) network' },
}

export function providerBrand(slug: string): ProviderBrand | null {
  const meta = NETWORKS[slug]
  if (!meta) return null
  return { name: meta.name, network: meta.network, logo: logoFor(slug) }
}

/** Frozen for V1: Chatr, Bell, Koodo, Freedom Mobile — one per network family
 *  (Rogers, Bell, TELUS, Freedom/Videotron). */
export const V1_PROVIDER_COUNT = Object.keys(NETWORKS).length
export const V1_NETWORK_FAMILY_COUNT = 4
