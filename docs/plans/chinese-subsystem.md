# Chinese · the subsystem beyond the schema

**Status:** not started, deliberately. What exists is the part that is painful to retrofit: every
record carries its `language`, a Chinese lexeme **requires** a `reading` (pinyin, on a prefix test so
`zh-Hant-TW` and `zho` match), and dictionaries, pictures, voices
and the map already work per language. What is not built is modelling how the language works — and
that is a subsystem, not a column, worth building once there are opinions from using the rest.

Three things about Chinese break the assumptions the model makes for Spanish:

1. **The unit of learning is not the word.** It is component ↔ character ↔ word — three levels. 妈妈 is
   a word made of a character made of components. Modelling it needs a lexeme→lexeme composition
   relation.
2. **Tone is not decoration.** mā / má / mǎ / mà are four different words, so a reading must be
   checked, not trusted (see the pinyin defect in [`article-quality.md`](article-quality.md)).
3. **Traditional and Simplified are a variant axis**, not a dialect.

**Why components are worth it.** 妈 (mā, mother) = 女 (woman) + 马 (mǎ, horse): the horse is there for
**sound**, the woman for meaning. This is a phono-semantic compound, and roughly 80% of characters are
built this way. The anchor European languages share through Latin and Greek roots has a real analogue
in Chinese; it lives *inside* the character rather than across languages.

To do, when Chinese is being learned in earnest: the composition relation, component modelling,
measure words, a corpus for Chinese in the retrieval service, photo capture's tap-on-a-character
([`photo-capture.md`](photo-capture.md), "Chinese and Japanese"), and the
Chinese views — a character network, a tone-pair grid, a syllable table
([`../research/similar-projects.md`](../research/similar-projects.md)).
