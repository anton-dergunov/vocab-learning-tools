# Vocabulary story generation

## Purpose

Generate short stories and exercises that reuse selected vocabulary in context.
The first output can be a standalone Markdown learning document. Story
generation should not depend on Anki, although Anki cards or another application
may consume the same story model later.

Stories complement individual vocabulary articles by exposing several words in
one coherent situation. They can reinforce collocations, grammatical forms,
register, and the relationship between words without repeating the format of a
flash card.

## Inputs

The generator selects validated vocabulary articles rather than scraping loose
Markdown with new regular expressions. Initial selection strategies can include:

- Explicit headwords supplied by the user.
- A fixed number of random entries with a recorded seed.
- Entries from one or more topics.
- Entries that have not appeared in a previous story.
- Later, entries selected from review history or learning priority.

The selection should preserve each article's headword, translation, examples,
and source topic. The source corpus must remain read-only.

## Generation workflow

```text
validated vocabulary corpus
            |
            v
select target entries
            |
            v
render versioned LLM prompt
            |
            v
generate structured story response
            |
            v
validate story and exercises
            |
            v
atomically write Markdown + metadata
```

The LLM should be created through the existing provider factory so Gemini,
Ollama, OpenAI-compatible services, or future providers can be selected through
the same configuration conventions as the vocabulary cleaner.

The provider should preferably return structured JSON. A validated internal
model can then render Markdown. Accepting arbitrary generated Markdown directly
would make it difficult to enforce required sections or detect missing target
words.

## Proposed story model

The exact model can be introduced when this feature is implemented, but it
should represent at least:

```text
StoryDocument
  id
  language
  title
  style
  target_entries[]
    headword
    translation
    source_topic
  story
  exercises
    fill_in_the_blank[]
    comprehension_questions[]
    translation_prompts[]
    retelling_prompt
  answer_key
  generation_metadata
```

Generation metadata should include the provider, model, prompt version or
checksum, selection seed, source article identities, creation time, and output
schema version. This makes a strange sentence or missing term traceable to the
inputs and generation settings.

## Markdown output

A generated document can use YAML front matter followed by readable sections:

```markdown
---
id: el-refugio-del-acertijo-20260825
language: Spanish
created_at: 2026-08-25T12:00:00Z
style: mystery
topics: [Emotions, Misc, Health]
target_words: [deprimido, acertijo, escalofriante, desmayarse]
provider: gemini
model: example-model
prompt_version: 1
selection_seed: 42
---

# El refugio del acertijo

## Story

...

## Target vocabulary

...

## Exercises

### Fill in the blanks

...

### Comprehension

...

### Translation

...

### Retelling

...

## Answer key

...
```

The output directory should be configurable. A reasonable default is
`output/stories/`, using a stable story identifier in the filename and refusing
to overwrite an unrelated existing document. A later story collection can add
an index by date, topic, or target word.

Markdown remains useful even if another presentation layer is introduced: it
is readable without the application, easy to publish, and can be converted to
HTML, PDF, an Anki note, or another format.

## Validation

Before publishing a story, validate that:

- The response conforms to the story schema.
- Every requested entry is represented in the target vocabulary list.
- The story and required exercise sections are non-empty.
- Exercise references and answer keys are internally consistent.
- No unexpected fields silently change the schema.
- The output path is safe and the final write is atomic.

Checking literal target-word occurrences in Spanish prose is not sufficient on
its own because an LLM may correctly inflect a verb or change number or gender.
The structured response can therefore include the actual form and a short
excerpt where each target entry was used. More sophisticated morphological
validation can be added later if useful.

If generation or validation fails, no partial story should be published. The
selected words and generation request should remain available for retry.

## Story and exercise options

Initial story controls can remain small:

- Target length, for example 100–300 words.
- Style such as mystery, comedy, travel, romance, or supernatural.
- Difficulty or expected learner level.
- Regional variety and register.
- Number and types of exercises.
- Desired repetition range for target vocabulary.

Exercise types can include fill-in-the-blank sentences, comprehension
questions, short translation prompts, a word-to-meaning match, and a retelling
prompt. They should be generated from the final validated story rather than
from an earlier draft.

## Possible command-line interface

```bash
python scripts/generate_story.py --topic Emotions --count 10 --seed 42
python scripts/generate_story.py --words añorar acertijo refugio --style mystery
python scripts/generate_story.py --config config/local.yaml --llm-provider ollama
```

The selection and rendering logic should be ordinary Python library code. A
future Prefect task can wrap the complete idempotent story-generation stage
without creating a separate implementation.

## Testing strategy

- Unit-test deterministic word selection with a fixed seed.
- Parse vocabulary through `ArticleShort` rather than test-only regexes.
- Use a fake LLM provider for schema, rendering, and failure tests.
- Write generated stories only under a temporary directory in automated tests.
- Assert that malformed or incomplete generation publishes no file.
- Keep real-provider story generation behind the existing slow-integration
  test gate.
- Test that repeated execution either reuses the same identified artifact or
  creates an explicitly new version according to the selected policy.

## Later extensions

- Select words according to spaced-review history.
- Generate a new story for words that remain difficult.
- Add narration using the existing TTS providers.
- Add one illustration or a sequence of scene illustrations.
- Publish a browsable static story library.
- Export selected exercises to Anki without making Anki the canonical format.
- Record story artifacts and their vocabulary dependencies in the future
  Prefect orchestration layer.
