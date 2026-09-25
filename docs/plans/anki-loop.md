# The Anki loop · closing it in both directions

**Status:** planned. The robot, the manifest contract and the state pull are built
([`../features/anki.md`](../features/anki.md)). What is missing is the loop itself: nothing turns the
vocabulary into a manifest, and nothing acts on the review state that comes back. Without both, Acervo
cannot say whether anything it does helps a word stick — the thing every competitor sells
([`../research/similar-projects.md`](../research/similar-projects.md), "The learning loop is not
closed").

## 1 · Cards out: a manifest from the vocabulary

A job that builds the manifest from the graph and hands it to the robot's `push`.

- **One deck per language**, `Spanish::Vocabulary`, with topics as `acervo::topic::…` tags. A split
  per topic stays possible as configuration (`Spanish::%topic`), but is not the default.
- **What a card carries**: the word, its gloss, the sentence worth keeping (the owner's own first, as
  the Obsidian mirror chooses), the sense's picture and the headword's recording.
- **Pictures at 768 px** (~70 KB) rather than the 1024 master, if deck size bites; check that WebP
  renders on AnkiMobile before committing thousands of files to it.
- **Open: sense-level or lexeme-level cards.** Sense-level cards are more correct and produce more
  cards; lexeme-level cards mean fewer reviews but blur polysemy. The choice decides the study-state
  join, so it comes first.
- Keep `.apkg` export for bootstrapping and disaster recovery: it is the only export that works when
  nothing else does.

## 2 · Statistics in: acting on FSRS

`studyStates` already arrive. What they should change:

| Signal | Source | Effect on the word |
|---|---|---|
| **Learned** | stability above a year | `status → learned`, out of active rotation |
| **Struggling** | high difficulty or many lapses | **gates expensive treatment** — extra pictures, clips, stories |
| **"I know this"** | a green flag, or a suspension | `status → learned`, overriding FSRS |
| **"This card is wrong"** | a red flag | back to `inbox` for regeneration |
| **Never scheduled** | no card | drift between the vocabulary and the deck |

Flags and suspension would need the robot to report them — today they are exported and deliberately
not stored. FSRS difficulty is the free answer to "which words deserve the expensive treatment",
with no marking discipline required.

## 3 · Running it

The nightly run already declares an `anki.pull` step and refuses to switch it on
([`../architecture/jobs.md`](../architecture/jobs.md)). Pull and push become nightly steps once
the two halves above exist.

## Open

- **Where the daily review happens.** Anki is a better scheduler; Acervo is a better place for LLM
  grading and clip playback. Likely both — but which one owns the daily session should be decided
  before building either side further. See also [`learning-modes.md`](learning-modes.md).
