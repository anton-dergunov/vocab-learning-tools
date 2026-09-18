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

…and the two for the loops surface:

- **Loops** — opens and closes it.
- **1× / 4× / 12×** — winds the loop's clock on. A word really takes twenty-two
  seconds; at 1× the reveal has its true rhythm, and at 12× a whole loop can be
  watched through in twenty seconds.

There is no audio and there will not be: a fake clock stands in for the track, so
the word being said, the translation arriving and the seek line are all driven by
exactly what drives them in the application. **A translation is never drawn before it has
been spoken** — an unreached word shows a short bar of a fixed width instead — and
the reveal is a pure function of that clock, so dragging backwards puts the answer
away again.

Deep links keep screenshots reproducible: `?open=la obra&frame=phone&view=cards&card=1`,
plus `tr=on`, `theme=dark`, and `size=375x667` to resize the frame.

For loops: `?loops=1&t=12` is the moment the whole design is for — `picar` is
being said and its translation is still a bar. `t=20` is a few seconds later,
with the answer given and the mark moved to it. `loop=` picks one by id,
`play=1` starts it and `speed=4` winds the clock on.
`la obra` and `animarse` are copied from a real account; `picar` sense 1 has a
deliberately overlong example, to show the one card that has to scroll.
`la sobremesa` is still being filled in on the server: it shows the progress strip, the clip slot
and the closed Cards switch. `fill=searching|none|failed|off` picks how its clip search ends.
`espolvorear` is deliberately the one Spanish word with no `primaryGloss`, so it is the one that
cannot be in a loop — a loop has to choose a single meaning, and nothing fills that in later.
Of the four loops, one has never been rendered and one was made on a server with no sample pack.
