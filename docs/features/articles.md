# Articles · reading a word, and editing it as a document

An article is one word as the owner reads it: the headword, its senses with their definitions and
glosses, the examples and the sentences the owner met it in, pictures, clips and recordings. It is
read in the article view and edited as a YAML document. The view models are `web/src/selectors.ts`,
the document is `web/src/yaml.ts`, the editor is `YamlPane.tsx`, and the one writer is
`repository.saveArticle`. Asking a model about an article is [`article-chat.md`](article-chat.md).

---

## One view model, two feeders, one renderer

`LexemeArticle.tsx` renders an `Article`, and there are exactly two ways to make one:

- **`articleFor(graph, lexemeId)`** assembles a stored word from the replica.
- **`articleFromDraft(graph, draft)`** assembles an unsaved proposal from a parsed document — a
  capture's draft, or a draft under edit.

So a generated entry is reviewed in the same component a stored one is read in, and approving a
proposal means reading the entry you are about to get. What `articleFromDraft` returns is
**render-only**: its placeholder ids are deliberately not valid record ids, so it can never be saved by
mistake. **Do not render an article by round-tripping stored records through YAML text**: the
projection is for editing and serialising, not for display.

**Two ways to read it.** *Page* is the whole article in one column; *Cards* is one sense at a time in
the same deck a story is read in. Which one an article opens in is a per-device preference — `auto` is
Cards on a touch screen, where a word is glanced at, and Page where there is a pointer — and the switch
above an article changes it for that sitting only. After a save the word opens in Page, because that is
where the reserved slots keep the layout still while clips and pictures arrive
([`../architecture/jobs.md`](../architecture/jobs.md), "What the interface shows").

## The document

**The YAML is a projection of the records, not a storage format.** Markdown and extended-article JSON
are not storage formats either; the records are. The document is how a word is edited and how it
travels in an export bundle, and `yaml.ts` is **the only place YAML is understood** — generated
documents arrive there on exactly the same footing as typed ones.

- **Both directions live in one module, through one library.** A hand-written serialiser paired with a
  parser drifts apart the first time someone adds a field to one of them.
- **It is lossless by test**: `parseArticle(yamlFor(article))` reproduces every editable field exactly.
  A field the serialiser forgets to write is a field the next save deletes, so this is the contract that
  makes editing safe.
- **Every record carries its id**, so a save is an exact diff rather than a guess: a record with an id
  is updated, one without is created, and one the document no longer mentions is tombstoned, a removed
  sense taking its examples and pictures with it. Ids are never recycled through an edit, which is what
  keeps the Anki join, derived ids and `createdAt` intact.
- **State is not in the document.** A picture's `attempts`, `failureReason` and `suppressed` are facts
  about what the server did, like `revision`, not things a document can assert; a save carries them
  through untouched, so editing YAML cannot un-suppress a picture or reset its attempts. Study state is
  written as **comments** — visible where you would look for it, impossible to save back.
- **Topics are written as names**, because a rail label is what someone editing can actually see.

### Gloss lines, and quoting for the strictest reader

A gloss is written in flow style — `{lang: en, terms: [to itch]}` — because it reads far better on one
line. But a flow collection is where plain scalars are most constrained, and *how* constrained depends on
the reader: the `yaml` package speaks YAML 1.2, where `?` is an indicator only at the start of a token,
while PyYAML speaks 1.1 and refuses it anywhere in a flow scalar. So `terms: [who is calling?, on the
line]` round-tripped perfectly through Acervo and could not be opened by any Python tool — five of 1,481
real word files were unreadable that way, in a repository that is half Python.

**The rule is deliberately conservative**, not a transcription of either spec: a term is left plain only
when it is letters, digits, spaces and a few marks no reader treats specially, and quoted otherwise.
Over-quoting costs two characters; under-quoting costs a file one reader cannot open.

## The editor

The YAML editor is **CodeMirror 6**, themed onto Acervo's palette and its mono measure. **CodeMirror owns
the caret and the glyphs together, which is the whole reason it is here.** A hand-written editor — a
transparent `<textarea>` laid over a separately rendered, highlighted copy of the same text — needs two
independent layouts to agree pixel for pixel, and every way they can disagree is a visible bug: text
drawn over text, a selection that stops short, typing that lands somewhere else. Fixing symptoms one at
a time does not fix the cause. **Do not reintroduce an overlay.**

- **Wrapping and line numbers are per-device preferences**, set in Settings rather than as controls
  above the editor, where they were things to step over on the way to work. Wrapping is the default,
  because these documents are mostly prose; scrolling stays available because YAML indentation matters.
- **The editor's colours and the prototype's must change together.** The prototype has no bundler, so
  it paints a static picture of the same surface; `YamlPane.tsx`'s theme and the prototype's styles are
  the one place the application and `design/ui-prototype/` legitimately differ, and they are kept in
  step by hand.
- **In Add, YAML is the document of record.** The Article tab is derived from the editor text on every
  keystroke, so the preview and the editor cannot drift apart ([`capture.md`](capture.md)).

## Saving

**There is one writer: `saveArticle(parseArticle(text))`**, for a typed edit, a capture, an approved chat
proposal and an import alike. It is one round trip to `POST /articles`, which diffs the parsed document
against the stored entry **on the server**, in one transaction, and returns the new revision. It sends
`base`, the revision this replica holds of each of the entry's records, so an edit made from a stale copy
is refused rather than laid over a newer one, and only records this device could have seen are
tombstoned ([`../architecture/sync.md`](../architecture/sync.md)).

- **A document that names no stored entry may carry ids its producer minted**, so records created
  together can reference each other; one editing a stored entry may not, and an unknown id there is
  refused. The single exception is chat's `minted` argument — an argument, not a field, so a hand-typed
  document cannot claim it — which lets an example drawn from a sentence you just supplied name its
  attestation in the same save.
- **Undo is the previous document saved again.** It works without special support because a removed
  child is tombstoned rather than erased, and naming a tombstoned id brings the record back.
- A save is online-only and all or nothing: a refusal leaves both the replica and the draft untouched.
