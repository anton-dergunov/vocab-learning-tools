# Acervo responsive icon family

The selected identity is the warm-red book treasury with `A` and `Ñ`. It uses
three optical sizes rather than shrinking one detailed bitmap everywhere:

| Display size | Artwork | Reason |
|---|---|---|
| 16–24 px | `source/favicon-micro.svg` / one `A` tile | One glyph and broad shapes survive browser-tab rasterization. |
| 32–96 px | `source/icon-small.png` / schematic `A` and `Ñ` | Preserves both letter tiles without page lines or texture. |
| 128 px and above | `source/icon-full.png` | Preserves the chosen detailed artwork. |

The canonical sources and every file under `dist/` are production assets and
should be committed. Exploratory concepts, rejected variants, generated
candidates, and pixel-test previews live under the ignored
`design/generated/` directory.

`dist/` contains ready-to-use PNG and ICO files, including:

- `favicon-16.png`, `favicon-24.png`, `favicon-32.png`, `favicon-48.png`,
  `favicon-64.png`, and `favicon-96.png`
- `favicon.ico` containing 16, 32, and 48 px images
- `favicon.svg`, the resolution-independent micro mark
- `apple-touch-icon.png` at 180 px
- `pwa-icon-192.png` and `pwa-icon-512.png`
- `pwa-maskable-192.png` and `pwa-maskable-512.png`
- general detailed exports from 128 through 1024 px

## Browser markup

When the web app is added, copy the required files from `dist/` into its public
icon directory and adjust the paths below:

```html
<link rel="icon" type="image/png" sizes="16x16" href="/icons/favicon-16.png">
<link rel="icon" type="image/png" sizes="32x32" href="/icons/favicon-32.png">
<link rel="icon" type="image/png" sizes="48x48" href="/icons/favicon-48.png">
<link rel="shortcut icon" href="/icons/favicon.ico">
<link rel="apple-touch-icon" sizes="180x180" href="/icons/apple-touch-icon.png">
```

Use the PNG declarations when optical-size switching matters. Declaring only
`favicon.svg` would make the one-tile micro treatment appear at every size.

## PWA manifest fragment

```json
{
  "icons": [
    {"src": "/icons/pwa-icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
    {"src": "/icons/pwa-icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
    {"src": "/icons/pwa-maskable-192.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
    {"src": "/icons/pwa-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}
  ]
}
```

The small and micro masters were derived with built-in image generation from the
selected full-size icon. The final 16 px mark was then redrawn as path-based SVG
to eliminate font substitution and retain crisp geometry.
