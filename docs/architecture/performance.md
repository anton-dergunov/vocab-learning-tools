# Performance · the write path, measured

What a save, a pull, an import and a cold start cost, and the four optimisations that are worth doing
only once a measurement says so. The replica's own rules — immutable and shared, validated by the
incoming records rather than the whole graph — are why the device side is cheap; see
[`sync.md`](sync.md).

## Measured

Against a real replica of 1,719 words (10.8k records, 7.9 MB). Device figures are from a laptop; a
tablet is several times slower. Each row is a cost the design keeps low, what keeps it low, and what
the obvious implementation measured instead.

| Operation | Cost | What keeps it there | The obvious way |
|---|---|---|---|
| Merging one saved word into the device's replica | 0.18 ms | The replica is immutable and shared: a merge replaces only the records and collections it changes, and validates only the incoming records (`validateChanges`) | Cloning the whole replica for each step and validating the whole graph: six clones and a full validation, ~190 ms per word — and it grew with every word, so an import slowed down as it went |
| The export panel repainting while an import runs beside it | 12 ms | Finding the pictures and clips to export walks every word, so it is memoised on the replica and the chosen language (`TransferPanel.tsx`) | Walking every word on every repaint: ~1,020 ms each time the import changed anything |
| The server restoring one imported picture | 90–210 ms | A picture in a bundle is already a master, so it is stored byte for byte (`images/render.as_master`) | Re-encoding it as WebP at `method=6`: 430–630 ms of the NAS's CPU per picture, most of a full import's half hour |
| Saving an article on the server | 22–30 ms | One transaction, and an update never rewrites a row's primary key | Writing `SET id = <the same id>`: with foreign keys on, SQLite treats that as a key change and scans every child index — seven for a lexeme, the whole `image_prompts` table for an example |
| An empty cursor pull | 17 ms over Tailscale | `GET /graph` is a pure read ([`server.md`](server.md), "Storage") | — |

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
