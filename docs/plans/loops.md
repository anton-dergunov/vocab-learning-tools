# Loops · what is still to do

**Status:** small and open. The design as built is [`../features/loops.md`](../features/loops.md).

- **Say when a render finishes.** Making a loop takes minutes and the owner walks away; today the only
  toast is "Making your loop — it takes a few minutes" when it starts. A toast with an action to listen,
  when the track lands, would close the loop.
- **More ways to choose the words** in the make dialog, one selector each: by difficulty once review
  state comes back ([`anki-loop.md`](anki-loop.md)), newest first, and "words with no loop yet".
- **LexiBeat's own default seed**, in the other repository. Given no seed, its generator uses
  `secrets.randbits(64)`, which cannot round-trip through JSON into a browser; 2^53 would do everything
  2^64 does, the seed being a replay token rather than a key. Acervo is unaffected, since it mints the
  seed itself — this is a fix to make there, at its next release.
