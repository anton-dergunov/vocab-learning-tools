# Are the stories any good?

**Status: open. Nothing here is built.** This is the question `experiments/story-quality/`
deliberately did not answer.

That experiment settled whether the pipeline *holds*: every word used literally, parts that fit a
screen, a translation that keeps its order, a character that stays in the same coat across four
pictures. All of that is mechanical, and all of it is now checked. Whether the stories are worth
reading is a different question with a different method, and it is the one that decides whether this
feature earns its place.

## Why it needs a method at all

Seven stories, read once, by the person who wrote the prompt, is not a measurement. Three things
make this harder than it looks:

- **A story you just watched being generated reads better than it is.** `compose-lesson-line/` found
  a **50% false-positive rate on same-arm controls** — readers confidently identified a difference
  between two outputs of the *identical* prompt half the time (κ = −0.10 against a Pro judge). Any
  method here has to carry same-arm controls or it is measuring nothing.
- **The temperature is 1.0**, so run-to-run variance is the highest of any call in Acervo. A prompt
  change has to beat that noise, not just differ from one sample.
- **"Good" is not one thing.** A story can be funny and teach nothing, or use every word perfectly
  and be a list of sentences.

## What "good" might mean

A first decomposition, to be argued with rather than adopted:

1. **Did I finish it?** The only measure that matters on its own. A story abandoned halfway taught
   nothing, whatever else was true of it.
2. **Did the ending land?** Round 2 of the experiment showed the failure clearly: stories that stop
   rather than end. This is the most improvable axis and probably the highest-value one.
3. **Are the words load-bearing?** Not just present — attached to what is happening, in a situation
   that shows what they mean. `empezar a susurrar un gruñido bajo` passes the mechanical check and
   fails this one.
4. **Is the language natural?** Forcing three words into twelve sentences bends prose. How often,
   and how badly, is unmeasured.
5. **Is it the kind it claimed to be?** `mystery` should be a mystery, not a story with a locked
   door in it. The type briefs are long and untested against each other.
6. **Would I read a second one?** Distinct from (1), and the one that predicts whether the feature
   is used at all.

## Things worth trying

- **Read them after a delay.** Recall a week later is closer to what the feature is for than an
  opinion on the day. It also breaks the same-arm false-positive effect, which depends on knowing
  the two arms exist.
- **A/B on the ending alone.** Cheapest high-value test: hold the story fixed and generate several
  final parts. Endings are separable in a way tone is not.
- **A judge model, calibrated against same-arm controls first.** If it cannot tell two samples of
  one prompt apart at chance, it is not a judge.
- **Does the word count change the quality?** The default is three. Nobody has checked whether five
  is worse, and the intuition that it is has no evidence behind it.
- **Do the pictures help?** They are the most expensive part. Whether a story with pictures is
  remembered better than one without is a real question that has never been asked.

## What is deliberately not the plan

Not a leaderboard of models — the owner's chain decides who answers, and a prompt tuned to one model
is a prompt that breaks when the free tier changes. Not an automated score checked in CI: a number
that nobody reads behind a story nobody reads is two problems.
