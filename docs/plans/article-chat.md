# Article chat · open questions

**Status:** small and open; none is blocking. The design as built is
[`../features/article-chat.md`](../features/article-chat.md).

- **Which neighbours to send.** Topic-mates is the obvious rule and probably enough. Same-lemma and
  headword-similar entries are cheap to add off the replica; whether they help is unmeasured.
- **Whether the reply should stream.** FastAPI can; it does not, for three reasons: the answer is one
  JSON object whose most valuable field is last, so streaming needs a streaming JSON parser to show
  anything; it would fork `provider.text(…, as_json=True)`'s complete-answer contract, and
  `chain.walk` cannot decide a 429 fall-through until enough has arrived to know it is not an error;
  and it would be the first route outside the `{"data": …}` envelope. A three-second wait under a quiet
  "thinking" line may well be fine. Measure before building anything.
- **Model-written or fixed follow-ups.** Model-written costs nothing and is more relevant; fixed presets
  are predictable. Model-written, until they turn out bland.
- **Whether the review count counts fields or records.** A sense whose definition *and* glosses moved is
  one change — right for accepting, arguable for stepping, since `‹ ›` cannot reach the second field.
- **The note-pairing constants**, a similarity of 0.5 and a three-token floor, are argued in
  `articleEdit.ts` and tuned only against fixtures, never real edits.
- **The prototype paints the review state by position.** `reviewMark` marks the first example and the
  second sense because it is a picture of the design, not a diff; if the marks grow much more
  structure, that picture will start to lie.
