# Article chat · round two, on the review surface

**Status:** Built. This records what using the feature on macOS, iOS and Android exposed, the ten
decisions taken in response, and what was deliberately left alone. The settled parts are folded into
[`acervo-llm-editing.md`](../acervo-llm-editing.md); this document is the reasoning, which does not
survive a diff.

---

## §1 · What real use exposed

The conversation and its proposals worked. The **review surface** did not, in one substantive way and
several mechanical ones.

### The substantive failure: a change you cannot see

A proposal said *what* it touched and never *what it did*.

- A reworded sentence was marked `changed`, and that was all. To find out which words moved you had
  to remember the old sentence.
- A reworded **note** did not even read as a change. It came back as a deletion beside an addition —
  because notes were matched by their text, so the pairing that would have let us diff them was
  thrown away before anything was rendered. The asymmetry with sentences was visible and unexplained:
  edit a sentence and it changes in place; edit a note and it is replaced.
- A **reorder** produced `count: 0`. The review bar said "0 changes proposed" over an article that had
  silently renumbered itself. `SENSE_FIELDS` has no `order`, senses match by a stable id, and the
  rendering walks `after`'s order — so every branch reported nothing while the page visibly moved.

### Mechanical defects, three of them never reported

| | |
| --- | --- |
| Marked text sat right of unmarked text | `.notes li.mark` doubled `padding-left` from 15px to 30px, so a marked note was indented past its neighbours while its em-dash stayed put. `.ex.mark` did the same by 2px. |
| `.mark::before` collided with the em-dash | `.notes li::before` and `.mark::before` are the same pseudo-element. The dash won `content` on specificity and then inherited the bar's `width: 3px` and its background — which is why a separate `.notes li.mark::after` had to be bolted on to draw the bar at all. |
| A changed sense shifted every example under it | `.sec.mark { padding-left: 14px }`. On the narrow layout `.sec` is one column, so a reworded definition moved the rail, the glosses and every example — including untouched ones — 14px right. The worst of the three, and the only one nobody had noticed. |
| The sheet reserved a large empty box | `.ask-half { height: 45dvh }`. Opening the conversation took nearly half the screen before there was anything in it, and past that the thread scrolled inside a box while empty space sat below. |
| Its largest detent left a useless strip | `calc(100dvh - 96px)` — a magic number that left one line of article above the sheet. On a phone and, as it turned out, on a desktop too. |
| The composer was squeezed to nothing | On Android the focus chip ("example 1 of sense 3"), the mark and the send button left the field about 180px. |
| The review bar wrapped to two rows | A `flex: 1` spacer plus `flex-wrap: wrap` put *Save changes* on its own line, eating 44px of article on the device with the least of it. |
| Two identical notes collided | Keyed by text, they shared one map entry — so one overwrote the other, the count was wrong, and React had a duplicate key. |
| Follow-ups included "Looks good" | Not a question and not an action. It spends the only one-tap slot there is on a phone on nothing. |

---

## §2 · Ten decisions

**1 · No mark may move body text.** The bar and glyph draw in the gutter a block already owns; the
glyph is absolutely positioned and is a direct child of the marked block, never inside a paragraph.
Where a block has no spare gutter — a note, whose 15px holds an em-dash — it borrows 14px from the
pane with an equal negative margin and pins the dash back, so the content edge does not move at all.
`.mark::before` is gone, which kills the collision at its root, and no `.mark` rule sets padding
except that one note case. The rule is written into the stylesheet above the `.mark` block, because
it cannot be tested: jsdom does no layout and the stylesheet is not loaded under test.

*Rejected:* replacing a marked note's em-dash with the mark. It makes the note stop looking like a
member of its own list, and 3px of bar plus 7px of glyph does not fit in 15px anyway.

**2 · A word-level inline diff, computed on the device.** Removed words struck through in rust,
inserted words in teal, in place. This is what makes `changed` mean something, and it is what turns a
reworded note from a delete-plus-add into one change. No model is asked what it did: a model's
account of its own edit is one more thing that can be wrong.

**3 · Word level, not character level**, and hand-written rather than a dependency. There is no diff
library in the tree, and a text-diff package would answer one of three questions — the other two,
the minimal moved set for a reorder and the note-similarity measure, need the raw LCS, which then
gets written anyway. One `lcs` serves all three.

`Intl.Segmenter` is the tokeniser, with a regex fallback. Not gold-plating: Chinese and Japanese
write without spaces, so `\p{L}+` makes 他把衣服穿上了 one token and the word diff would report
"everything replaced" for exactly the languages a learner needs it in most.

**4 · Only the field that changed gets the tint.** A changed definition tints the definition; the
sense keeps its rail bar to say something inside it moved. Tinting a whole sense would claim its
untouched examples changed, which is the one thing a diff must not do. Small blocks — an example, an
attestation, a note — still tint whole, because there the changed content *is* the block. That is
also the fix for the note complaint: a changed note used to get a bar and nothing else, so it read as
quieter than a changed example for no reason.

**5 · `moved` is its own mark.** The rail reads `↕ 01` with `was 02` beneath, it counts as a change,
and it gets no tint because none of its content changed. Which senses moved is the **complement of
the longest increasing subsequence**, not "everything in a different position" — rotating three
senses is one drag and reports one change.

**6 · One uniform operation vocabulary.** `add` / `set` / `remove` / `reorder`, each with a `target`.
`target` names a record — `lexeme`, or `<kind>:<id>` — except on `add` and `reorder`, where the record
does not exist yet and it names a kind. The parent is a named field (`after`, `in`) rather than
something encoded in the operation's name. This is legibility rather than accuracy: the old names
worked. It is cheap because the operations are a wire format for one request and `diffDrafts` reads
drafts rather than operations.

**7 · The focus chip gets its own row.** It is context, not part of the input. One layout at every
width, and the field gets its full width back on the device that needed it. The send button stays
everywhere — it is the affordance people reach for first, and dropping it on narrow would have made
the phone a different layout to explain.

**8 · The review bar never wraps.** `flex-wrap: nowrap`; on a phone the sentence shortens to
`3 changes` and *Save changes* to *Save*. It also gains `‹ 1/3 ›` next to the counter, so the counter
tells you where you are while you step through — and a proposal below the fold is reachable rather
than merely reported.

**9 · The largest detent is available at every width.** Once it actually hides the article there is no
reason to withhold it on a desktop: the useless one-line strip it replaces was a desktop defect too.
One state machine, nothing width-dependent to explain or test.

The mechanism is `.main.composing`, which already exists for the YAML editor and the Add view — *a
surface that owns the height and scrolls itself must not sit inside a region that also scrolls.*
`overflow: hidden` clamps `scrollTop` to zero, so the article's offset is parked on the way in and
restored on the way out: four lines. *Rejected:* `position: fixed` with insets. `.viewport` sets
`container-type: inline-size`, making it the containing block for fixed descendants, so the insets
would have to clear a topbar on one layout and a topbar plus a dynamic rail height on the other.

**10 · The follow-up ban is stated and enforced.** The prompt forbids acknowledgements; `_shaped`
drops one whose whole string, casefolded and stripped of punctuation, is in a frozen set. Whole-string
only, never substring — *"Thanks, now add an example"* must survive. This follows the rule §5.3 sets
for itself: a cap the model cannot argue with is worth more than a paragraph it can.

---

## §3 · What the live run changed

Two findings only a real model could produce, both in the prompt rather than the code.

**A volunteered sentence stopped being proposed.** Strengthening "a question is not a request to
change anything" over-corrected: *"I heard this on the radio: «…»"* started coming back as prose. The
fix is an explicit two-column gate — turn on the left, `proposal` or none on the right — with the
volunteered-sentence rows marked **yes** and a paragraph saying why: *they went to the trouble of
typing it.*

**A comparison question reliably proposes, and the design said it should not.** §5.3 says a question
gets prose and no proposal. Three prompt revisions later, `gemini-3.1-flash-lite` still offers to add
the contrast to the notes every time. The honest conclusion is that this is the wrong thing to
assert: a proposal is **offered**, not applied — nothing is written without a press on *Review* and a
second on *Save* — so an unasked-for proposal is a pre-computed follow-up, and the contract worth
holding is not "never volunteer" but "never rewrite what is already there unasked".

`test_it_answers_a_question_without_rewriting_anything` now asserts that: at most two operations, no
invented ids, and if it touches anything it may only *add to* the notes, keeping every line already
there. The prompt still asks for the stricter behaviour, because the guidance is right even where the
model is unreliable. A coin-flip assertion is worse than an honest one.

---

## §4 · What was left alone

- **No side pane, at any width.** §7.1 stands. The article column is 780px against an 834px tablet.
- **No streaming, still.** The reasons changed at the end of round one and none of them moved here.
- **No per-owner rate floor.** Still no machinery for one, and still no need.
- **The YAML tab stays unmarked.** It is the escape hatch, not the review surface; gutter decorations
  there answer a question the Article tab already answered.
- **`matchedForm` is never tinted.** `realign()` may drop it as a side effect of setting `text`, so
  marking it would report a change nobody asked for. The example's own block mark still shows.
- **A marked example loses `.ex.own`'s teal.** The border carries the mark for the length of the
  review; the `origin` chip in the foot still says `attestation`. A review is transient and one
  signal per gutter is the limit.
- **The Add view cannot reach the largest detent.** That surface is itself a review, and its
  `Composer` already owns the height — there is nothing for the sheet to take over.
- **No keyboard shortcuts for next and previous.** They would fight the composer, which is where the
  hands already are.

---

## §5 · Still open

- **Whether `count` should count fields or records.** A sense whose definition *and* glosses moved is
  one change today. That is right for accepting — it is one thing to judge — and arguable for
  stepping, since `‹ ›` then cannot reach the second field. Nobody has wanted it yet.
- **Similarity pairing has two constants**, 0.5 and three tokens. They are argued in
  `articleEdit.ts` and neither has been tuned against real edits, only against the fixtures.
- **The prototype paints the review state positionally.** `reviewMark` marks the first example and
  the second sense because it is a picture of the design, not a diff. If the marks grow much more
  structure, that picture will start to lie.
