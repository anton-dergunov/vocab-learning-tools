# Durability · what protects the vocabulary

Losing this costs years of curation no amount of compute can reconstruct, so the threat model is taken
seriously — and the real threat is not a dead disk. It is **logical corruption that replicates**: a bad
change or a mis-tap removes 200 words, and by the time anyone notices every device has faithfully
agreed.

What is not built yet — scheduled snapshots, an automated off-machine export, backups of media and the
Anki collection, restore drills, and rebuilding the server from a device — is
[`../plans/backups.md`](../plans/backups.md).

---

## Tombstones are never collected

A deleted word stays *in* the database with `deleted` set, and so do its senses, examples and
everything else under it. So an accidental deletion — even "Delete all words" — is recoverable by a
data edit: write the records again un-deleted, and the server stamps them with a higher revision, so
they beat the tombstone on every device. At ten thousand words the storage cost is nil, and it buys an
undo that survives everything. Undo after a chat edit works the same way, which is why a removed child
is tombstoned rather than erased.

**Restoring the server does not undo a deletion.** Undoing a logical delete is a data edit; restoring a
snapshot is a different procedure for a different failure. They feel identical from the outside.

## What exists

- **The replicas.** Every device holds a complete copy. Devices never push, so a replica does not
  repair a restored server by itself — it is *evidence*: enough to see what was lost, and the copy to
  rebuild from by hand.
- **A database backup on every deploy.** `install.sh` copies the vocabulary database and the Anki
  files into `backups/<UTC timestamp>/` under the deployment root before anything changes, and keeps
  the ten newest. A schema transition prints that path twice. The copy is taken with the server
  stopped; a live WAL-mode database is backed up with `sqlite3 .backup`, never `cp`, which is the
  classic route to a backup that looks fine until the day it is needed.
- **The export bundle.** Settings ▸ Data writes a zip of the whole vocabulary as a *different
  representation*: one YAML file per word under its language, in exactly the document the editor reads,
  plus an Obsidian mirror ([`../features/export.md`](../features/export.md)). It survives a schema bug
  that corrupts the database, and it restores without any of this software working. One file per word
  means a git history of the tree is the complete edit history of each word.

## Restoring

**A restore must mint a new `datasetId`.** The revision sequence restarts, so a device holding an old
cursor is asking for revisions the restored database has not reached: without the guard it pulls
nothing, reports itself in sync, and shows a collection no other device can see. Because the identity
is the `sync_state` row's id, a rebuilt database gets a new one for free; a restore into an existing
database must change it deliberately.

**A new `datasetId` stops every device rather than resetting it**, because there is nothing to re-push
and discarding a replica could throw away the most complete copy left. So a restore has a manual step
by design:

1. Restore the snapshot. Every device notices and stops syncing.
2. Decide, per device, which copy is more complete — the devices are the evidence.
3. Either rebuild the server from the best replica, or accept the snapshot and let each device
   replace its copy with the server's.

That manual step is the price of online-only writes, and worth paying: it costs a step in a rare
procedure and buys the absence of merge conflicts in the everyday one.

## What is not backed up

- **Media** — pictures and recordings, 2–10 GB — is not copied into the dated deploy backups. It is
  regenerable in principle, at real cost in time and provider allowance.
- **The corpus's index** is rebuilt from the captions whenever the service updates.
- **The caption cache and the channel catalogue are not regenerable, and no deploy backup covers
  them.** The caption cache cost bandwidth to download and cannot politely be fetched again at will;
  nothing in either repository deletes it. The channel catalogue is a mount the retrieval service
  seeded once and the owner has edited since. Their backup is the operator's
  ([`../features/spoken-clips.md`](../features/spoken-clips.md) §2.3).
