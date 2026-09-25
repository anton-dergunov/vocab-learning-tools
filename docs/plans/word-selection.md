# Word selection · what it could serve next

**Status:** open design questions. The selection as built — a device-local, per-language, ordered pile
feeding loops and stories — is [`../features/word-selection.md`](../features/word-selection.md).
Selection was built for two consumers; most of what follows is whether it should grow more, and
what each would cost the model it has now.

## More things to make from a pile

Each is a consumer, and each should be a button on the bar or an item in its list, never a second
selection mechanism.

- **Ask about them together.** "How do these differ?" across three near-synonyms is the question the
  article conversation cannot ask today, because it is scoped to one word. A selection is the natural
  scope — but it would need the chat's document to become several entries, which touches the edit
  language.
- **File them.** Put every selected word under a topic, or take it out of one. Cheap: an ordinary graph
  write per word. It is also the likeliest way the pile becomes curation — see the next section.
- **Send them to Anki first**, or mark them to study, once the Anki loop exists
  ([`anki-loop.md`](anki-loop.md)).
- **Export just these** — a bundle of the pile, for handing a set of words to someone.
- **A collage.** One picture made from the selected words, the way a story is made from them: a new job
  kind whose output is a media file and a record naming it.
- **Suppress or delete them in bulk.** Useful, and the most dangerous; it wants the same live counts and
  typed confirmation "Delete all words" has, and undo.

## The questions that change the model

- **Should a selection ever sync?** Today it does not, and the cost is a pile gathered on the tablet
  being absent from the phone. Syncing it means a replicated record — a schema bump, a write route, and a
  selection that can conflict — for something meant to be thrown away. Worth it only if piles turn out
  to live for days rather than an hour.
- **Should a selection be nameable, or kept?** "Words I keep confusing", kept for weeks, is a topic in all
  but name. The honest answer may be that a kept selection *is* a topic, and the gesture is *Save as
  topic* — which keeps one filing system rather than two.
- **Selecting from a search or a filter.** "Select everything matching" is the bulk-tick the design
  deliberately avoids, but "select the twelve weakest words in this topic" — once review state arrives —
  is a pile nobody could gather by hand. It would be a consumer of study state, not of checkboxes.
- **Selection across languages.** Rejected for now because loops and stories are single-language; a
  consumer that is not (export, filing) might want it, and the per-language store would have to say how.
