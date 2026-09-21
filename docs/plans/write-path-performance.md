# Write-path performance: what is left, if it matters

Status: **not started**. The options below are only worth doing if a measurement shows they would
help. The fixes that were clearly needed are already in; this page keeps the rest from being lost.

## What was fixed, and what it was worth

Measured against a real replica of 1,719 words (10.8k records, 7.9 MB). The device figures are
from a laptop, and a tablet is several times slower.

| | Before | After |
|---|---|---|
| Device work to merge one saved word | ~190 ms (six whole-replica clones and a full validation) | 0.18 ms |
| Export panel, on every repaint beside a running import | ~1,020 ms | 12 ms |
| Server, restoring one imported picture | 430–630 ms (re-encoded at WebP `method=6`) | 90–210 ms (stored byte for byte) |
| Server, a new brief: from the `revision` frame to the job's `done` | — | same 10 ms; the dialog's wait had been on the device |

The rest of the server path was already cheap: an article save takes 22–30 ms and an empty pull
17 ms over Tailscale. Updates also stopped rewriting the primary key, which with foreign keys on
made SQLite scan every child index on each edit.

## Options

**1. Save only what changed.** `services/articles.save_article` rewrites every record of an entry,
with a new revision, even when a record is unchanged. Skipping any record whose fields equal the
stored row would mean fewer writes, a smaller reply, and fewer revisions for every other device to
pull. The `base` stale check is unaffected, because it compares revisions and does not write.
*Worth it when:* editing a large word feels slow, or other devices visibly re-pull whole entries
after a typo fix.

**2. Pipeline the import.** Each word waits for its save, then its pictures one at a time, then its
clips, then its enrichment request. The options are to upload a word's pictures 2–3 at a time, or
to keep two words in flight. Either hides round trips rather than removing work, and the server
serialises writes anyway. *Worth it when:* a full-bundle import still takes more than a few minutes
now that a picture costs ~100–200 ms. Time a real import first.

**3. A cheaper WebP encode for drawn pictures.** `images/render.encode_master` uses `method=6`,
which is about twice the cost of `method=4` (0.24 s vs 0.12 s on the laptop, more on the NAS). The
encode happens inside a model call that takes seconds, so it is barely visible. *Worth it only
with* a blind size and quality comparison, like `experiments/pronunciation-encoding/` did for
audio.

**4. The cold-start read.** Opening after iOS has evicted the app reads the whole replica from
IndexedDB before the first word can be shown. That wait is now covered by a launch screen, and it
is measured on the device: Settings ▸ Sync says `Opened in … — reading N records … · checking … ·
first list …`. If the read dominates, one option is a small first-paint cache of the last list (one
language's headwords and glosses) in local storage, shown until the replica arrives. Another is to
load the heavy collections (examples, image prompts) after the list is on screen. Both add a second
path to the same data, so both need the tablet's number first.
