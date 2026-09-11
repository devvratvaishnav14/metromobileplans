# Social / icon source art

Original artwork for the browser tab icon and the social-share preview.
Concept: a map location pin whose face carries a mobile-signal mark. No carrier
logos. Palette matches the app (map-blue + results-navy).

| Source | Rendered asset(s) in `/public` |
|---|---|
| `icon-rounded.svg` | `favicon.svg`, `favicon-32.png`, `favicon-16.png` |
| `icon-fullbleed.svg` | `apple-touch-icon.png`, `icon-192.png`, `icon-512.png` |
| `og-image.svg` (1200×1200 canvas, safe area is the middle 630 band) | `og-image.png` (1200×630) |

## Re-rendering (macOS, no extra tooling)

`qlmanage` (QuickLook) rasterises SVG; `sips` crops/resizes. Render large, then
downscale:

```sh
# icons
sed 's/SIZE/1024/g' icon-fullbleed.svg > /tmp/i.svg
qlmanage -t -s 1024 -o /tmp /tmp/i.svg
sips -s format png -z 180 180 /tmp/i.svg.png --out ../../public/apple-touch-icon.png

# og image (square canvas -> centre-crop to 1200x630)
qlmanage -t -s 1200 -o /tmp og-image.svg
sips -c 630 1200 /tmp/og-image.svg.png --out ../../public/og-image.png
```

QuickLook ignores SVG gradients, so the art uses flat fills / stacked shapes.
