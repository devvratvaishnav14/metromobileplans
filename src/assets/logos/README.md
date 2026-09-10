# Provider logos (drop-in)

Put each carrier's **official** logo here, named by provider slug:

| file | provider |
|---|---|
| `chatr.svg` (or `.png` / `.webp`) | Chatr |
| `bell.svg` | Bell |
| `koodo.svg` | Koodo |
| `freedom-mobile.svg` | Freedom Mobile |

`src/analysis/providers.ts` loads whatever is present via `import.meta.glob`,
so no code change is needed. If a file is missing, that card just shows the
provider name + network text with no image.

Source each file from the carrier's own site or official brand/press kit.
Do not trace, redraw, or recreate a logo. The results page carries a
disclaimer that this is an independent comparison, not affiliated with or
endorsed by any carrier.

Recommended: an SVG (or a transparent PNG at ~2× the ~32px display height).
Keep the intrinsic aspect ratio; the UI constrains height, not width.
