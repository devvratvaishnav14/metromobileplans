import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

/**
 * Absolute, canonical site URL for <link rel="canonical"> and the Open Graph /
 * Twitter tags in index.html. Set VITE_SITE_URL in the deploy environment (or a
 * local .env) when the site moves to its own domain; the Vercel URL is the
 * current default. The API base URL is separate — see VITE_API_BASE_URL.
 */
const DEFAULT_SITE_URL = 'https://metromobileplans.vercel.app'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = { ...process.env, ...loadEnv(mode, process.cwd(), 'VITE_') }
  const siteUrl = (env.VITE_SITE_URL || DEFAULT_SITE_URL).replace(/\/$/, '')

  return {
    plugins: [
      react(),
      {
        name: 'inject-site-url',
        transformIndexHtml: {
          order: 'pre',
          handler: (html) => html.replaceAll('%SITE_URL%', siteUrl),
        },
      },
    ],
  }
})
