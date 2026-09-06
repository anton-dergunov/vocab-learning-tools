# Round 6 · 2026-09-06

The overnight run, reviewed at ~100 images. Prompt version `img-d53d0537f12f-ab741596e...` — the
style hints removed, text allowed unless it gives the answer away, gender required, the word
prioritised over the sentence. **98 of 100 kept.**

## What the earlier fixes did

Each of these was a failure in an earlier round and each is now reported as working:

| Fix | Round 6 |
|---|---|
| Gender written into the brief | *"I haven't seen a case yet when the gender would be misassigned."* |
| Text allowed unless it is the answer | Lettering appears in a dozen pictures — an exam crib, a price display, a road sign — and *"I didn't see any case when somebody would reveal the actual word."* The verb-conjugation and return-ticket failures of round 5 are gone. |
| Draw the word, not only the sentence | *"Can I understand the sense of this word just by looking at the image? Usually yes."* |
| `situation` before the brief | Abstract sentences that produced diagrams now produce scenes. |
| Batch a lexeme's senses in one call | `estar en llamas` drew a literal burning warehouse for one sense and a social-media firestorm for the other, unprompted. The cross-sense contrast §03 was built for. |

**On style variety, without hints:** *"Surprisingly I wouldn't say they are all uniform... the styles
are on point and chosen according to the needs of the sentence."* `art-nouveau`, which had never been
chosen in 227 images, arrived unforced on *she had been carrying the baby in her womb for eight
months* and was judged apt. The distribution is still uneven (§ round 5), but unevenness and
wrongness turn out to be different complaints, and only the second one matters.

## 12 · The gloss is not the word

**`estar fundado`** — *tener su base, origen o justificación principal en algo determinado*. Nothing
in that definition is physical and nothing is about earth. Glossed into English as "to be grounded
in", the situation became an elderly foundry owner showing an apprentice the **bedrock pillars** in a
sub-basement. That is a picture of the English word *ground*.

The model reads English better than Spanish and will reach for the gloss when the definition is
harder work. The template now states the hierarchy outright — the definition in the language being
learned is the authority, glosses are hints that can mislead — and the definition is now labelled
with its language in the request so the distinction is visible rather than implied.

## 13 · Drift compounds across the steps

The same failure has a second half. The sentence suggests a situation, the situation suggests a
scene, the scene suggests detail, and four steps on the picture is about something else — the
apprentice named in the situation is not even in the final image.

Added: **read the situation back against the original definition before writing the brief**, and fix
the situation rather than elaborating the drift.

## 14 · A metaphor is only as good as its vehicle

**`estar hasta las narices`** — fed up. The situation was right: *a commuter utterly fed up after
waiting day after day*. The brief then buried him **to the nose in bus tickets**, and the pile reads
as banknotes. The picture says "rich", or "corrupt", well before it says "fed up" — and the trench
coat pushes it further toward a spy thriller.

Added: choose the object, then look at it cold and ask what a stranger would call it. If the honest
answer is a different word, choose a different object.

## 15 · Carry the facts, do not enlarge the asides

The tickets have a second cause. *Todos los días* — every day — is the sentence's texture, not its
subject, and depicting it as a quantity produced the clutter. One weary person at one bus stop was
the picture.

The rule has an explicit exception, because round 3 established the opposite for a different case:
when the qualifier **is** the target word, repetition is the whole picture. *A menudo* keeps its five
ghosted figures.

## Smaller additions from the review

- **Reinforcing props.** A thick rope looped between people at a family dinner, for *fortalecer
  vínculos*. A second element quietly restating the meaning makes a picture land harder — as long as
  it is a second voice, not a competing idea.
- **Never specify exact figures or wording.** The model cannot render a given string: ask for "a
  price on the till display", not "€85". Two pictures were marked down for miscounting — 13 guests
  drawn as 14, twenty chapters as thirty — and neither needed the number to be right.
- **Wordplay counts as a joke.** For a bare number or a function word with nothing to picture, a pun
  on the word can be a stronger hook than any literal scene. That is how people actually remember
  vocabulary.
