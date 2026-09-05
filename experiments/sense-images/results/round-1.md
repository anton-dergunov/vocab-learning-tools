# Round 1 · 2026-09-05

14 senses, 8 Spanish words, prompt version `img-d3f4f5622ed2-6578b5997ee5-c3f7d5`. Seven kept, seven
rejected. Rejected files and their records are preserved under `output/images/round-1-rejected/`.

**The image model is not the problem.** Every one of the fourteen is beautifully painted; several
would pass as work by a real artist. What follows is entirely about the text the brief writer hands
it.

| Word | Sense | Style | Verdict |
|---|---|---|---|
| a menudo | often, frequently | baroque-chiaroscuro | **rejected** — no frequency anywhere in the frame |
| a pie | on foot | stained-glass | **rejected** — static boots, no walking; glass style reads as painted-on |
| abonar | to pay, settle | watercolour-storybook | kept — a coin over a counter, works |
| abonar | to fertilise | art-nouveau | kept, weakly — reads as magic, not as feeding soil |
| abundar | to be plentiful | baroque-chiaroscuro | **rejected** — depicts the *opposite* (see below) |
| abundar | to be rich in | ukiyo-e | kept — over-exaggerated but the meaning lands |
| abundar | to dwell on a topic | golden-hour | **rejected** — weavers in a workshop; no teacher, no class, no elaborating |
| acariciar | to stroke, pet | golden-hour | kept — the best of the batch |
| acariciar | to entertain an idea | baroque-chiaroscuro | **rejected** — wrong gender, and duty rather than pleasure |
| acechar | to stalk, lie in wait | golden-hour | kept — cat, window, birds; the sentence honoured |
| acechar | danger lurks | watercolour-storybook | **rejected** — a pleasant forest with no threat in it |
| acogedor | cosy (of a place) | anime-cel | kept — cosy, but a home rather than the café in the sentence |
| acogedor | welcoming (of people) | stained-glass | kept, weakly — the meaning lands, the sentence does not |
| aconsejar | to advise | gouache-poster | **rejected** — gives directions rather than counsel |

## Four systematic failures

### 1 · The style authors the scene

The single largest cause, and it is behind five of the seven rejections. The style brief is meant to
say **how the picture is painted**. It is instead deciding **what is in it** — the era, the setting,
the cast, the time of day, the architecture.

- *a menudo*, "she often studies in the library" → baroque-chiaroscuro produced a candle-lit
  antiquarian room with no person and no library. The reviewer's objection is exact: at that
  apparent date a public library of the kind the sentence means did not exist.
- *abundar*, "olive groves and vineyards abound in this region" → baroque produced a night scene of
  a poorly dressed, frightened woman among grapes. Nobody harvests at night. She reads as a thief.
  The picture depicts scarcity and fear — **the antonym of the word**.
- *acogedor*, "the family was very welcoming" → stained-glass produced a church. Stained glass
  implies a building, so the model put one in.
- *acariciar*, "she had been entertaining the idea of travelling" → baroque produced a man, not a
  woman, and read as a soldier planning a hard march rather than anyone enjoying a daydream.

The pattern: a period style drags the scene into that period, and an architectural style drags the
scene into that architecture. Neither was asked for and both silently overrule the sentence.

### 2 · The style is assigned, not chosen

Sampling three styles by weight and letting the writer pick one of the three still means the *scene*
is being written to fit a style that arrived at random. Baroque drew three of the fourteen and three
of the seven rejections. The reviewer's conclusion, and it is right: **offer every style and let the
writer choose the one that suits the meaning**, rather than making it argue with a dice roll.

The pedagogical case for variety in §09 of the design is unaffected — variety is still wanted. What
round 1 shows is that random *assignment* buys variety at the cost of meaning, which is the wrong
trade for the only thing the picture is for.

### 3 · The brief drifts from the example sentence

Given a sentence, the writer treats it as a theme rather than a scene, and the concrete facts in it
go missing.

| Sentence | What was drawn |
|---|---|
| She often studies in the library | Books. No woman, no library, no studying. |
| He likes to pet the dog while resting on the sofa | Hand and dog outdoors. No sofa, no indoors. |
| The teacher wanted to elaborate before the class ended | A workshop of weavers. No teacher, no class. |
| The family was very welcoming during the trip | Two glass hands in a church. No family, no guests. |
| She had been entertaining the idea for months | A man with a military map. |

The instruction that licensed this — *"if a different scene expresses the same sense more vividly,
build that instead"* — was written for the sense with no example. Applied to a sense that has one, it
throws away the learner's own context, which is the part with memory already attached to it.

### 4 · The word's meaning is not depicted

The accent rule was read as *"make one object large and luminous"*. That is composition, not
meaning, and for a whole class of words it cannot work.

- *a menudo* means **frequency**. A glowing book is a picture of a book. Frequency has to be *shown*:
  the same act repeated across the frame, a tally, wear accumulated by repetition, a sequence.
- *acechar* (danger lurks) means a **threat is present but concealed**. A pleasant forest with an odd
  tree root has no threat in it. Something has to be lurking.
- *abundar en un tema* means **to elaborate, to go on about**. Silent weavers cooperating is not
  elaboration; nobody in the frame is even speaking.
- *aconsejar* means **counsel**, judgement offered about a situation. Pointing at a route is
  directions.

### And one over-correction

*abundar* "the river abounds in trout" packed the frame so densely there is no water left. The
exaggeration instruction is working, but it is being spent on the *scene* rather than on the
**word**. Push the element that carries the meaning; leave the rest plausible.

## Style-table change

**`stained-glass` is removed.** Two appearances, two problems: it forces a church interior, and the
boots it drew looked painted onto glass rather than made of it. It is the one style whose medium
cannot help implying a building.

`baroque-chiaroscuro` is kept. It is not a bad style — it is the style that best exposed failure 1,
and once the style stops authoring the scene it should behave like any other.
