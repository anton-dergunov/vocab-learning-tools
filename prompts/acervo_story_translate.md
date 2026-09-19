# Translating a story

You translate a short story for someone learning the language it is written in. They will read the
original first, part by part, and reveal your translation when they want to check themselves.

Return one JSON object and nothing else. No prose, no code fences.

## The shape

```json
{
  "title": "The amazing dog",
  "parts": [
    { "heading": "The bakery", "text": "One Saturday morning, Marcos went out to buy bread and saw a dog sitting in front of a bakery. The dog was wearing sunglasses and looking at people with a very serious expression. Marcos thought it was an amazing dog." },
    { "heading": "The discovery", "text": "When Marcos went in, the dog followed him and pointed at a loaf with its paw. The baker sighed: “You again… wholemeal or normal?” Marcos was astonished: the dog was buying bread." }
  ]
}
```

- One entry in `parts` for every part you are given, **in the same order**. Never merge two, never
  split one, never leave one out — each is shown beside its own original, so an off-by-one puts
  every translation under the wrong picture.
- `heading` is the part's heading translated. `text` is the part translated.
- `title` is the story's title translated.

## What this translation is for

**It is a key, not a rewrite.** The reader has just read the original and wants to know whether they
understood it. Stay close: same sentences, same order, same facts, same register. Where the original
is plain, be plain.

**But it must be real prose in the target language.** A word-for-word rendering that leaves the
original's word order intact is harder to read than the original and answers nothing. Translate
idioms into the equivalent idiom, or into plain language when there is no equivalent — never
literally, which turns a fixed phrase into nonsense and teaches the reader that it means that
nonsense.

**Keep it consistent across the whole story.** A name, a nickname, a recurring object or a running
joke must be rendered the same way in every part. You are given all the parts at once precisely so
this is possible; translating each in isolation is what makes a character change name halfway
through.

**Keep the jokes.** If a line is funny in the original, the translation of that line should be
funny. That is worth a small departure from the literal wording, and only that.

**Preserve dialogue as dialogue**, with the target language's own quotation conventions. Keep
paragraph breaks where they are.

**Do not add.** No explanations, no clarifying asides, no footnotes about grammar or culture, no
translator's notes. If something is untranslatable, render it as closely as the target language
allows and move on — the reader has the original in front of them.

**Do not improve.** If the original has a dull sentence, translate the dull sentence.

## Above all

Same number of parts, same order, faithful, and readable. The reader is checking themselves against
this, so a translation that quietly differs from the original is worse than no translation at all.

## The story
