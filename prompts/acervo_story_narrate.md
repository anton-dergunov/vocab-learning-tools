# Preparing a story part to be read aloud

You are given one part of a short story in the language a learner is studying. It will be read aloud
by a voice that can be told *how* to read each stretch of text. Your job is to cut the part into
passages and, for each, say how it should be read.

Return one JSON object and nothing else. No prose, no code fences.

## The shape

```json
{
  "segments": [
    { "text": "Cada martes a las seis de la mañana, Mateo abría su pequeño taller en el puerto de Vigo.", "direction": "Calm and unhurried, like the start of a bedtime story." },
    { "text": "Durante cincuenta años, su familia se había dedicado a salar el pescado fresco.", "direction": "Warm and a little proud, at an even pace." }
  ]
}
```

## The one rule that matters

**Do not change the text.** Every `text` is copied from the part *exactly*: the same words, the same
spelling, the same punctuation, the same quotation marks and capital letters, in the same order.
Do not fix a typo, do not translate, do not shorten, do not reword, do not skip a sentence, do not
add a word. If you put the segments' `text` one after another with a space between them, you must
get the part back, character for character. The part is checked against your answer, and anything you
alter is read in a flat default voice instead of yours.

## How to cut it

- A passage is usually **one sentence**. Split a long sentence only where the *feeling* changes — a
  quoted line of speech inside narration, a turn ("Sin embargo, …"), a punchline.
- A line of **dialogue is its own segment**, with its quotation marks, and its direction says who is
  speaking and how ("A grumpy old man, muttering." "Bright and excited.").
- Never cut in the middle of a phrase where the voice would have to stop for breath and start again.
- Aim for **three to eight segments** for a part of two to four sentences. Never more than twelve.

## The direction

One short sentence, in **English**, telling a voice actor how to read that passage: the feeling, the
pace, the energy. Be specific and vary it — a story is not read in one mood. Good directions:

- "Hushed and suspicious, slowing down on the last few words."
- "Deadpan, as if stating the most ordinary fact in the world."
- "Breathless with excitement, speeding up."
- "Warm and wistful, almost a whisper."

Do not describe the content ("about a cat"), do not write a full instruction to a person, and do not
put the direction in the language of the story.
