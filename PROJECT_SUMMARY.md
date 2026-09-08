# Project summary: vocab-learning-tools

A personal toolkit for building foreign-language (Spanish) vocabulary study material with LLMs. It's a work-in-progress mid-refactor: a clean, tested library (`src/vocabgen/`) is emerging out of older one-off prototype scripts.

## Two pipelines

### 1. Inbox cleaner — `scripts/clean_vocab.py` (the mature, working one)

The end-to-end flow in `main()`:

- Recursively merges an optional local YAML overlay over tracked defaults, selects a configured LLM provider (with a CLI override), then renders that provider's Jinja2 system prompt.
- Loads the raw *inbox* through `DraftInbox`, splits it on `---`-style separators, and creates a timestamped backup.
- Parses existing per-topic articles with `ArticleShort` to validate them and index every existing headword (`scan_topic_files_for_titles`).
- Processes sections in batches through an LLM, splitting the response back into articles, then for each article: extracts the `Topic:` line, detects **exact** duplicates (skip) and **fuzzy** duplicates via `difflib` (still appended, but flagged), and appends new ones to `…- %topic.md` files via atomic/append file ops.
- Requires exactly one generated article per requested inbox section, then atomically removes a batch only after validation and all output writes succeed. Incomplete, failed, malformed, or partially persisted batches remain available for safe retry.
- Prints a summary + detailed conflict report.

### 2. Anki deck generator — `scripts/generate_anki_deck_draft.py`

The `preview` subcommand validates `ArticleExtended` JSON and renders standalone HTML without loading Anki or media backends. The `build` subcommand creates configured TTS/image providers once, atomically generates missing deterministic cache files, builds one word note plus one note per meaning with deterministic GUIDs, embeds every media file, and writes the `.apkg` atomically. Configured and CLI-relative paths resolve from the repository root.

## The library (`src/vocabgen/`)

- **Provider factory** (`provider/factory.py`) — **superseded, and reachable only from tests.** Dynamic dispatch: `create_provider("llm", {"provider":"gemini",...})` imports `vocabgen.llm.gemini.GeminiProvider`. Three families, each an ABC + backends: `llm/` (`openai`, `gemini`, `ollama`, each `generate(system, user)` wrapped with `@retry()` and a `RateLimiter`), `tts/` (`kokoro` → mp3 with silence padding via `helpers.py`), `vision/` (`stable_diffusion` → resized jpg). No production script imports any of it.
- **Where model calls actually happen**, in four unrelated places: `images/` and `scripts/generate_images.py` (direct `google-genai` against Vertex), `image_benchmark/` and `scripts/image_benchmark_runner.py` (a subprocess registry of eleven backends), and the PocketBase capture hook (raw HTTP). Consolidating all four onto one catalogue and one Python package is planned in `docs/plans/`.
- **Cross-cutting** `provider/`: `retry.py` (exponential backoff + jitter) and `rate_limiter.py` (sliding-window, not thread-safe — `images/pacing.py` is the thread-safe fork that the live pipeline uses).
- **Core logic** `vocab_processor.py` (pure parsing/matching functions) and **isolated I/O** `fileops.py` (atomic write, append, backup, slugify).
- **Data classes** `data/`: `ArticleShort` (validated Markdown), `DraftInbox` (mutable inbox wrapper), and Pydantic v2 `ArticleExtended`/nested models (validated canonical JSON). `ArticleExtendedCollection` manages JSON files and `MediaCollection` manages generated media caches.
- **Anki library** `anki/`: deterministic media paths/generation, stable note identities and package building, and lightweight standalone HTML previews.

## Test state

Healthy: unit tests cover the processor, data models, provider architecture, failure-safe cleaner, deterministic Anki builder, media caching/packaging, HTML preview, Kokoro, and Stable Diffusion. Integration tests are double-gated (`RUN_SLOW_INTEGRATION_TESTS` + API key/model); manual scripts exist for ad-hoc LLM/media testing.

## Signs of an in-progress refactor

- **Shared parsing helpers**: `normalize_separator_line`/`split_sections` now live in `sections.py` and are used by both the maintained CLI's `DraftInbox` and `vocab_processor.py`.
- **Many `# TODO`/`# FIXME` markers** still flag known rough edges (factory typing, config-type checks, shared cleaner helpers).
- **Tracked integration corpus**: `test-data/` contains realistic topic files
  and a raw inbox. Integration tests operate on temporary copies.
- **Future story output**: `docs/story_generation.md` specifies validated,
  provider-independent story and exercise generation with Markdown as the
  first publishing format.
- **Dependency groups**: the default requirements are core-only;
  `requirements/media.txt` adds Anki/TTS/vision and `requirements/dev.txt`
  provides the complete test environment.
- **Scratch/legacy data** (untracked or gitignored): `old_prototypes/`,
  `checking/`, `venv_bad/`, and `test-data-bkp/`.
**In short:** both pipelines now use validated domain models. The remaining roughness is concentrated in configuration typing, the four unrelated places a model is actually called from, and the still-manual transition from short Markdown articles to extended JSON.
