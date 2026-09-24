# Word selection

Words put aside, by hand, to make something from. Today that is a loop or a story. Until now
both could only be made from words drawn at random from whatever the list was showing. Later,
selection will probably serve other things. The design of record is the prototype
(`design/ui-prototype/`, `?select=1`).

## What was asked for

The owner's spoken note, restated as requirements.

1. **Mark, don't tick.** A word joins the selection through an explicit action: a row's
   right-click menu, a swipe, or a button on the article or the map. It is not ⌘-click and it is
   not checkboxes. A vocabulary of a thousand words across a dozen topics is not a list anyone
   ticks through. A checkbox also raises questions a mark does not have: what happens to it when
   the topic changes, or when you search?
2. **The selection outlives navigation.** Changing topic, searching, opening an article or the map,
   and reloading all leave it alone. It belongs to **this device** and is never synced.
3. **One language.** A loop and a story are each in one language, so there is one selection per
   vocabulary language. The bar shows the selection for the language on screen.
4. **One row mechanism for words, loops and stories.** A pointer right-clicks a row for a menu. A
   finger swipes the row right-to-left to reveal the same actions, with Delete in red. Word rows
   offer *Add to / Remove from selection* and *Delete*. Loops and stories offer *Delete*.
5. **Selected words look selected**, in the list and on the map. The mark is distinct from hover
   and from the open row, and it moves nothing.
6. **The article.** A Select toggle sits beside Delete on a wide screen. On a phone it is an item
   in the ⋯ menu, above "Delete this word".
7. **The map.** The peek card has a Select toggle, and the map itself marks what is selected.
8. **A selection bar at every width.** It shows what is selected (an icon, the count, as many words
   as fit, then "+N"), **Loop** and **Story** on the right, and **×** to forget the selection. On a
   phone it takes the place of the Loops / Stories / Map bar.
9. **Making from it.** Loop and Story open the existing dialogs. Those dialogs show the actual
   words chosen rather than "N random words".
10. **After making, the selection is kept**, so the same words can also become a story or a second
    loop. Only × clears it.

## Decisions

- **Device-local, per language, in the order chosen.** The store is `web/src/selection.ts`, kept
  in local storage under the account it was made in. It is not replicated state, so it does not
  touch `LOCAL_SCHEMA_VERSION`. An entry is a lexeme id. A word deleted since it was chosen simply
  stops appearing, and nothing repairs the store.
- **The bar is never over an article or Add.** That column's foot belongs to the ask dock (design
  §2.13, the rule `MadeBar.tsx` already follows). Over an article, the article's own Select button
  shows the state, and toggling it says so in a toast. The bar is drawn over the list and the map.
  A loop that is playing on a phone keeps its bar, under the selection bar: hiding what is sounding
  would be worse than a second row.
- **One mark, in two places.** A selected row's plate is ringed in `--core`, with a gap of the
  page's paper, and wears a check badge at its lower right. The ring is a `box-shadow` and the badge
  is absolutely placed, so the word, the gloss and the row height never move. The map uses the same
  badge on a sense's emoji once it is zoomed in far enough to show emoji. Further out it draws a
  ring around the dot, which reads differently from Find's plain filled dots. Selected senses are
  always labelled and never dimmed. Every sense of a selected word is marked, because selection is
  of words and a map is of senses.
- **Forgetting is undoable.** × clears the selection at once, and the toast offers Undo. A selection
  can be twenty words gathered over an hour, and a single mistaken tap should not throw that away.
- **The bar's text opens the whole list.** Each word there can be opened or taken out, so removing
  one word does not mean finding it again among a thousand.
- **The dialogs say exactly what will be sent.** When a selection exists, a switch offers **Your
  selection · N** or **Random from {scope}**. The switch starts on the selection when the dialog
  was opened from the bar, and on the random draw when it was opened from a surface's own Make
  button.
  - The selection is shown as chips in the order the words were chosen.
  - A word the kind cannot use is struck through, and a sentence names it and says why. For a
    loop that is a word with no `primaryGloss`. Words past the limit are struck through too; the
    limits are the loop schema's `maxItems` and a story's `maxWords`, and the first words chosen
    are the ones used.
  - The button counts only the words it will send.
- **No server change.** `POST /loops` and `POST /stories` already take `lexemeIds` and never
  re-derive the scope.
