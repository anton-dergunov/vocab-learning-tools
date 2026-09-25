# Write-path performance · what is left, if it matters

**Status:** not started, and deliberately so. What was fixed, and what it was worth, is
[`../architecture/performance.md`](../architecture/performance.md). Each option below is worth doing only
once a measurement shows it would help.

- **Save only what changed.** `save_article` gives every record of an entry a new revision even when
  it is unchanged. Skipping equal records means fewer writes and less for other devices to pull; the
  `base` check is unaffected. *When* editing a large word feels slow, or a typo fix visibly re-pulls
  whole entries elsewhere.
- **Pipeline the import** — a word's pictures two or three at a time, or two words in flight. It
  hides round trips rather than removing work. *When* a full-bundle import still takes more than a
  few minutes; time one first.
- **A cheaper WebP encode.** `method=6` costs about twice `method=4` (0.24 s against 0.12 s on the
  laptop), inside a model call that takes seconds. *Only with* a blind size and quality comparison,
  as audio had.
- **A first-paint cache for cold start** — the last list's headwords and glosses in local storage,
  or the heavy collections loaded after the list. Both are a second path to the same data. *When*
  the tablet's figure in Settings ▸ Sync says the replica read dominates.
