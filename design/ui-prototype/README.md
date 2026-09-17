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
The preview frames count as touch screens: listen buttons stay visible and the
card arrows are hidden, as they would be on a real phone.

It also carries the switches for the article redesign spike:

- **View** — `auto` (Cards in the phone and tablet frames, Page on desktop),
  `page` or `cards`; stands in for a Settings option.
- **▷ Translations** — listen buttons after translations as well.

Deep links keep screenshots reproducible: `?open=la obra&frame=phone&view=cards&card=1`,
plus `tr=on`, `theme=dark`, and `size=375x667` to resize the frame.
`la obra` and `animarse` are copied from a real account; `picar` sense 1 has a
deliberately overlong example, to show the one card that has to scroll.
`la sobremesa` is still being filled in on the server: it shows the progress strip, the clip slot
and the closed Cards switch. `fill=searching|none|failed|off` picks how its clip search ends.
