# Performance · the write path, measured

What a save, a pull, an import and a cold start cost, and the four optimisations that are worth doing
only once a measurement says so. The replica's own rules — immutable and shared, validated by the
incoming records rather than the whole graph — are why the device side is cheap; see
[`sync.md`](sync.md).

## Measured

Measured against a real replica of 1,719 words (10.8k records, 7.9 MB); device figures are from a
laptop, and a tablet is several times slower.

| | Before | After |
|---|---|---|
| Device work to merge one saved word | ~190 ms (six whole-replica clones and a full validation) | 0.18 ms |
| Export panel, on every repaint beside a running import | ~1,020 ms | 12 ms |
| Server, restoring one imported picture | 430–630 ms (re-encoded at WebP `method=6`) | 90–210 ms (stored byte for byte) |

The rest was already cheap: an article save takes 22–30 ms and an empty pull 17 ms over Tailscale.
Updates also stopped rewriting the primary key, which with foreign keys on made SQLite scan every
child index on each edit.

## Not done, and what would justify each

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
