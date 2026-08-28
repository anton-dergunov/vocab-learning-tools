# Acervo — UI prototype

Static mock-up of the main window. Open `index.html` directly in a browser; no
server, no build step, no network calls (web fonts aside).

- `index.html` — shell
- `acervo.css` — design language lifted from the Acervo design-document artifact
  (Literata / IBM Plex Sans / IBM Plex Mono, paper-and-teal palette, light and dark)
- `data.js` — fixtures shaped like `web/src/domain.ts`
- `app.js` — view logic only; every write, TTS call and capture action is a stub
- `install.html` — the mobile installation gate, with iOS and Android preview links
- `img/` — sample generated illustrations, reused from the image benchmark

The floating control in the bottom-right previews phone and tablet widths inside
a desktop browser. It is prototype scaffolding and is not part of the design.
