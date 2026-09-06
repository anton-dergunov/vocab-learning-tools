# Round 5 · 2026-09-05

100 new senses, first round under the two-step brief (`situation` before `brief`) and the first on
`gemini-3.8-flash` rather than `gemini-3.1-flash-lite`. **97 of 100 kept.**

Clean run: 100 drawn, 0 refused, 0 failed, **0 quota waits**. Setting `--rate-limit 1` to the
measured ceiling means the runner paces itself instead of discovering the wall, so nothing is spent
on requests that will be refused and nothing is lost to exhausted retries the way `adosado` was in
round 4.

## The two-step brief works, and so does the bigger model

The reviewer's repeated note across the batch: *"I think the situation is working for us here."*
Sentences that produced diagrams in round 4 now produce scenes.

| Sentence | Round 4 | Round 5 |
|---|---|---|
| Your comment didn't bother me; on the contrary it helped me a lot | an arrow and a broken speech bubble | a woman pumping a colleague's hand while he flinches against the wall, braced for the row that did not come |
| Sometimes it's hard for me to understand grammar | rejected | kept — *"everything is perfect in this image"* |

It is not possible to separate the two changes: `situation` and the stronger model landed together.
The reviewer's read is that the model is contributing — *"more nuanced and more thoughtful pictures,
more going on behind them"* — and `estar al margen`, a politician standing apart from a scene he is
part of, is the example that suggests it is right. Worth remembering as a confound if either is ever
questioned.

## 9 · The style hints backfired

Round 4 added a `when` to every style, to unstick three that had never been chosen. It unstuck
`manga-panel` and broke the distribution:

| | round 4 | round 5 |
|---|---:|---:|
| distinct styles | 20/23 | 17/23 |
| top two combined | 35% | **44%** (claymation 23, comic-book 21) |
| baroque-chiaroscuro | 14 | 1 |
| pixar-3d, constructivist-poster, vintage-botanical | 6 / 6 / 2 | **0** |

The writer read `when` as a **matching rule** rather than a hint. `claymation`'s hint said "everyday
domestic objects", and a great many sentences are about everyday domestic objects, so a great many
became clay. The reviewer traced individual pictures to individual hint phrases —
*"do you really think I didn't notice"* went film-noir on "suspicion, surveillance, guilt", which
produced a domestic scene where a woman confronts her husband in an overcoat.

Two contributing causes, both ours:

- The template said *"if a scene would be just as well served by clay, woodblock, gouache or
  charcoal, use that instead"* — naming clay first, in the only sentence that told the writer to
  reach past the safe styles.
- The joke rule, promoted in round 4, points at exactly the two styles that spiked.

**`when` is no longer sent.** It stays in `image-styles.yaml` as a record of intent. The two styles
still never chosen in 227 images — `art-nouveau` and `retro-futurism` — get broader *descriptions*
instead, in the text the model does see, because that is the lever that does not double as a
matching rule. The template now asks directly for a flat distribution: between two styles that both
fit, take the rarer.

## 10 · The blanket text ban was costing pictures

Three round-5 pictures failed because the brief could not ask for writing that the scene needed:

- *In class we learned to conjugate irregular verbs* — a man wrestling nothing. **Rejected.**
- *On all trips it is advisable to buy return tickets* — blank diagrams handed over instead of
  tickets.
- *It is a colloquial expression used a lot among friends* — no way to show an expression.

The rule was never really "no text". It is **never the answer**: not the headword, not its lemma,
not a translation, not the example sentence, and no caption explaining the picture. Everything
else — a ticket, a price on a till, a verb table on a board, a street sign — is allowed where the
situation is about it. Lettering stays short and incidental, because the model draws long text as
mush.

## 11 · The word, not just the sentence

Two rejections and several weak keeps share one shape: the sentence is drawn and the *word* is not.

- *¿Cuánto vas a cobrar por arreglar la bicicleta?* — a repair shop, empty pockets, and a raised hand
  that reads as a threat rather than a price. **Rejected.** The word is *cobrar*, so money changing
  hands has to be the loudest thing in the frame.
- *Necesitamos al menos tres personas* — three people starting a game, but nothing makes *a minimum*
  visible.

Added: if you can draw the sentence without drawing the word, you have drawn the wrong picture.

## Smaller fixes

- **`papercraft-diorama` put every scene in a picture frame** — "a shallow box" in its description
  was doing it. Rewritten: the paper is the world, never a box or frame around it.
- **Invented detail reads as significant.** A heap of pink erasers across half a table pulled the eye
  off the subject. Every object named must be the subject, from the sentence, or needed to make the
  place legible.
- **The contact sheet is now newest-first and labels each image with its prompt revision.**
  Alphabetical order scattered each round through the whole sheet, so reviewing "what changed" meant
  scrolling past everything already judged and guessing which was which.
