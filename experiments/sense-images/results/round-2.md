# Round 2 · 2026-09-05

The same 14 senses as round 1, redrawn under prompt version `img-ae38ccde2ea9-9ff734a1feb1`, plus 3
new words the ingestion added while round 1 was being reviewed. Round 1's files are preserved under
`output/images/round-1-rejected/` and `output/images/round-1-kept/`, so every one of the fourteen is
a direct A/B on the same sense.

## The four failures, checked

| Round 1 failure | Round 2 |
|---|---|
| **1 · style authors the scene** | Fixed. `abonar` is a modern office, not a medieval merchant. `acogedor` is a café, not a home. No style relocated a scene. |
| **2 · style assigned at random** | Fixed by construction — the writer now sees all 23 and chooses. See the new problem below. |
| **3 · drift from the sentence** | Fixed. The sofa is in `acariciar`. The teacher and the class are in `abundar #3`. The family greeting a traveller is in `acogedor #2`. The gender is right. |
| **4 · meaning not depicted** | Fixed, and this is the striking one. `a menudo` is the same woman ghosted in five overlapping poses at one library desk — frequency *depicted*, not implied. `acechar #2` is a claw-shaped shadow with nothing casting it. `a pie` is mid-stride with motion blur. |
| over-exaggeration | Dialled back. The trout river is still thick with trout and still has water. |

The antonym check earned its place immediately: round 1's `abundar` was a frightened woman stealing
grapes at night; round 2 is a sunlit valley of olive groves and vineyards to the horizon with a
contented farmer harvesting.

## Two new problems

### 5 · Free choice collapsed the variety

Across 17 live images the writer used **5 styles of 23**:

| Count | Style |
|---:|---|
| 7 | cinematic-photoreal |
| 4 | golden-hour |
| 4 | baroque-chiaroscuro |
| 1 | watercolour-storybook |
| 1 | surrealism |

Two thirds are photographic. This is the cost that random assignment was paying for, and §09 of the
design is explicit that visual sameness across hundreds of cards destroys the distinctiveness that
makes the images work at all.

Variety *within* a word is healthy — `abundar` drew three different styles, and `acechar`,
`acogedor`, `acariciar` and `abonar` two each — because one call sees all the senses. The collapse is
*across* words, where each call is blind to every other.

Two changes rather than reverting to sampling:

- **The offered list is rotated per lexeme.** `cinematic-photoreal` is the first row of the table and
  was being read as the default. Rotation costs nothing and removes a position bias that was doing
  work fitness was supposed to do.
- **A weak hint**, as the reviewer proposed: photoreal and golden-hour are the answer when nothing
  else suits, not the first reach. Fitness still wins over novelty.

### 6 · The brief asked for text, so the picture has text

`a pie` reads "a digital clock on a building facade counting down", and the image has legible orange
digits — `00:03 / 00:02 / 00:01` — in the upper right.

The no-text rule was binding the *picture* and not the *brief*. A brief that puts a clock, a screen,
a sign or an open book in the scene and then forbids text is a contradiction, and the model resolves
it by drawing the text. The rule now names those objects and offers the alternative: show elapsed
time with light, wear or a shadow's length.

## Verdict

Round 2 is a clear pass on what round 1 rejected. Both new problems are prompt-level and both are
already patched; neither needs the images redrawn to be believed, so round 3 should be **new** words
rather than a third pass over these fourteen.
