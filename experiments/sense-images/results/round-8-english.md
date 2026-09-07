# Round 8 · 2026-09-07 · English validation

20 senses, the first drawn for the English vocabulary (definitions in English, glosses into Russian),
into a separate run directory. **17 of 20 kept** — a lower rate than the last Spanish rounds, and the
reason is instructive.

## What carried over unchanged

- **Per-lexeme batching earns more here than in Spanish.** English polysemy is sharper and the
  contrast landed every time: `acrid` drew stinging smoke for the literal sense and a corrosive
  remark for the figurative; `aggravation` split into a re-injured shoulder and boiling frustration;
  `admonish` into a mother's earnest grip and a teacher's raised finger.
- **The Russian glosses did not steer anything.** The worry going in was §12 in reverse — but here
  the definition is in English, the model's strongest language, and Russian is only a hint.
- **Style choice was judged sound**, including `oil-painting` at 6 of 20. The reviewer's reading is
  that the *word list* differs rather than the language: an advanced English vocabulary of
  `abysmal`, `affront`, `amiability` leans literary in a way the Spanish everyday vocabulary did not.

## Why the reject rate rose: the words are harder

The reviewer's diagnosis, and it reframes all three failures: this English vocabulary is **rarer and
more precise** than the Spanish one — it is a list of words for someone who already speaks the
language well. The whole value of such an entry is the *shade* of meaning, and a picture of the
general area teaches nothing.

### 18 · The qualifier that distinguishes the sense must be in the frame

**`abyss`**, sense 2: *the country was standing on the edge of an economic abyss.* Drawn as a city
avenue shearing into a bottomless void. A fine picture of an abyss — and nothing in it is
**economic**, so it cannot be told apart from the literal cliff drawn for sense 1.

A sense is separated from its siblings by one or two words, and those are exactly the words a picture
drops. Added: read the definition, ask which words are doing the distinguishing, and check that each
has something in the frame answering to it — a plunging market board, shuttered shopfronts, a bank
queue at the lip of the drop.

### 19 · A quality of speech lives in the listener, not in the air

**`acrid`**, sense 2: *she made an acrid remark about his lack of effort.* Drawn as a ribbon of
chartreuse vapour streaming from her lips, blistering the desk varnish, the young man turning away.

It reads as **halitosis**, immediately and unmistakably — a person recoiling from someone's mouth has
one overwhelmingly common cause, and it beats the intended reading outright.

This narrows the template's flagship technique rather than contradicting it. Giving an abstraction a
physical body still works — venom beading on a fang, ink soaking a floorboard. What fails is
**anything the body emits**: vapour, breath, smoke or fluid from a mouth has a literal reading that
wins. For a quality of speech, draw what the words *do* — the listener's face as it lands, a hand
stopped halfway to a cup, the others looking anywhere else, the speaker perfectly composed.

### 20 · Concrete but hard to draw is not the same as abstract

**`affinity`**, sense 1: *there is a close affinity between Spanish and Portuguese.* The sentence names
two real things and a real relation; it is simply hard to picture. Treated as abstract, it became a
scene *around* the idea — a philologist, an archive table, a brass lamp, two antique volumes — which
illustrates philology and leaves the affinity unshown. The image model then merged the two books into
one three-sided object, a second failure on top.

Added: stay literal and put the relation on the page. Similarity is **two things side by side whose
resemblance is the subject** — two faces mid-conversation understanding each other perfectly, two
nearly identical objects with one small difference. And give the pair real separation, because asking
for two near-identical objects touching invites exactly the merge that happened here.

---

## The full English run · 2026-09-07

848 of 851 senses. **50 reviewed, none rejected.**

| | |
|---|---:|
| Drawn | 848 |
| Refused by the writer | 2 — `molest`, `molestation` |
| Blocked by the provider | 1 — `snort`, the cocaine sense |

The two refusals are the narrow rule working. Both are the child-abuse sense, where there genuinely
is no scene that means the word without depicting what is forbidden — the rare case the rule
reserves, and unlike `joder` they were not overridden. Two other words the reviewer expected to be
declined, `warbag` and the vile-treatment sense of `vile`, were drawn safely.

### 21 · Ten senses were lost to an unpaced text call

Every one of the run's ten failures was `brief failed — 429`, on the **text** model. The image path
had a pace gate and twelve retries; the brief path had neither, so one text-quota refusal lost every
sense of that lexeme. The brief writer now backs off on quota — and only on quota, so a malformed
reply still fails at once rather than being retried six times.

A provider block is now terminal too, recorded as `blocked` on the record. `snort` would otherwise
have been re-planned on every future run, spending a text call and an image call to rediscover the
same block, exactly as `joder` was before refusals became terminal.

## The style question, resolved

Eight rounds argued about the distribution. The reviewer's verdict on the final 50 settles it:

> *"Even though we do have classes that are overrepresented, the choice of style according to the
> word was nice."*

English ended at 22 of 23 styles with 42% in the top two — `oil-painting` 210, `comic-book` 150 —
more concentrated than Spanish and leaning literary. The explanation is the **word list**, not the
language: an advanced English vocabulary of `abysmal`, `vitriolic`, `vindication` pulls toward
painterly registers, and the reviewer names the individual choices as apt each time.

So the conclusion is that **evenness was the wrong thing to measure.** A flat histogram was never the
goal; distinctiveness across a deck was, and it is achieved by 22 styles being *available and
correctly chosen*, not by each appearing equally often. `film-noir` for surveillance, `vintage-
botanical` for a worm in soil, photoreal for a weeping burn — the concentration is a property of what
the words are about.

`experiments/sense-images/style_distribution.py` and its chart stay as the record of how that was
established, including the finding that concentration appeared in every era and was never caused by
the hints.
