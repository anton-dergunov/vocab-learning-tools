# Acervo responsive icon family

The original warm-red open-book treasury with `A` and `Ñ` remains the
authoritative application artwork. It is preserved without alteration at larger
sizes. Only the smallest browser and menu-bar marks use a separate closed-book
optical size, because the full open-book silhouette does not survive at 16–32 px.

| Display size | Artwork | Reason |
|---|---|---|
| 16–32 px | `source/favicon-micro.svg` / closed burgundy book and `A` | Broad shapes survive browser-tab rasterization. |
| 48–96 px | `source/icon-small.png` / schematic open-book artwork | Retains the existing approved intermediate artwork. |
| 128 px and above | `source/icon-full.png` | Retains the original detailed artwork exactly. |

`scripts/generate_acervo_icons.py` regenerates only the 16, 24, and 32 px
favicon exports plus the multi-size ICO. It deliberately never modifies the
approved 48px-and-larger artwork. All files under `dist/` are production assets and
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

The micro master uses path-based geometry, including the letter `A`, so its
generation is deterministic and never depends on font substitution.
