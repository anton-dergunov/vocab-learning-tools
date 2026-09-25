# Anki · cards out, review state back

Acervo does not schedule reviews. Anki with FSRS is a better scheduler than anything worth building
here, so the vocabulary goes out to Anki as cards and Anki's memory state comes back as a report. The
consumer is `src/acervo/consumers/anki/`; setting it up is
[`../operations/anki-sync.md`](../operations/anki-sync.md); what is not built yet — turning the
vocabulary into cards automatically, and acting on what comes back — is
[`../plans/anki-loop.md`](../plans/anki-loop.md).

---

## Content out, statistics in, never both ways

Anki does not own "is this word learned": it reports, and the core decides. Bidirectional content sync
between a structured store and a flashcard collection is the swamp that eats these projects, so card
content flows one way and FSRS state flows the other.

## The desktop is not in the loop

Study happens on a tablet, essentially always, so a design that needs Anki Desktop running is the
wrong one however convenient it looks.

> **DECISION: self-host Anki's own sync server on the NAS, and update the collection with a headless
> robot client. AnkiConnect is not the design.**

Anki ships a sync server of its own; AnkiDroid and AnkiMobile point at a custom one in their settings.
That removes the media quota — the limit becomes the tablet's storage — and takes the desktop out of
the loop entirely. The server sits behind Tailscale rather than exposed.

**The robot is just another sync client.** Writing into the sync server's collection file would fight
the server for the same SQLite, so the robot keeps its own collection on the NAS and behaves exactly
like the tablet:

```text
robot (acervo-worker, one-shot)
  ├─ open its local collection
  ├─ sync DOWN from the server
  ├─ add / update notes from a manifest
  ├─ read back FSRS state            → studyStates, through POST /graph
  └─ sync UP
```

From the server's side this is indistinguishable from the iPad syncing, so conflict resolution is
Anki's own. It runs in the one-shot `acervo-worker` container — `run-worker.sh push`, `pull-state`,
`export-state` — through the reviewed launcher, and writes through the owner's own account.

**Four risks it is built around:**

1. **The sync protocol is version-locked.** The server and the robot run the same pinned `anki`
   image, upgraded as a pair; an unattended mismatch is the likeliest silent break.
2. **"Requires full sync" is dangerous for a robot.** A schema or deck-config change forces a full
   upload or download, and a robot that resolved it automatically could push a stale collection over
   real progress on the tablet. The robot fails loudly instead, and a person decides.
3. **Always sync down before changing anything; never force an upload.** Edits made mid-review merge
   correctly only if the robot behaves as a client, not an authority.
4. **Reachability.** The tablet reaches the NAS from outside the house over Tailscale.

## The manifest

Cards go in through a versioned manifest — one entry per note, carrying the lexeme id, the deck, the
front and back text, managed tags in the `acervo::` namespace, and relative paths to an image and
audio. Media is imported under content-addressed names. A duplicate identity fails before anything is
changed, and notes absent from a manifest are left untouched. The contract is in
[`../operations/anki-sync.md`](../operations/anki-sync.md), "Manifest contract".

**The join is an explicit hidden field, `AcervoNoteId`, on every note** — never a GUID derived from
content. A content-derived GUID breaks the day a template improves or a typo is fixed, quietly and
after the fact; an explicit id survives every edit, template change and re-import.

**One deck per language, topics as tags.** Per-topic decks multiply scheduling configuration — each
deck carries its own daily limits, fragmenting the queue — and do not reduce media, since every deck
in a collection shares one media folder.

## Review state back

`anki pull-state` writes one `studyStates` row per word and system: Anki's note and card ids and the
scheduler's reps, lapses, stability, difficulty, retrievability and last review, written through
`POST /graph` like any other client write. Rows are keyed by system so a second learning tool never
collides with Anki. `export-state` prints the same reading without writing it.

- **Retrievability is Anki's own number**, asked for only when there is a memory state to compute it
  from — an unset protobuf float reads as `0.0`, and a card FSRS knows nothing about would otherwise
  report itself as certainly forgotten.
- **Anki's review furniture is not stored.** Queue, suspension and flags have no column; inventing
  columns would mean rebuilding the database for information nothing reads.
- **Study state is read-only in the application.** It is a report from the scheduler, not a field to
  correct: nothing in the interface edits it, the YAML projection shows it only as comments, and it is
  deliberately left out of the export bundle.

**Review history is as irreplaceable as the vocabulary** — years of FSRS state cannot be regenerated —
so the Anki collection is backed up with every deploy ([`../architecture/durability.md`](../architecture/durability.md)).
