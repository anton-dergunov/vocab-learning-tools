# Prefect orchestration architecture

## Decision

The vocabulary system will first be implemented as ordinary Python library
code with explicit, independently testable stages. Prefect can then be added as
an optional orchestration layer over those stages.

Prefect must not contain a second implementation of the vocabulary logic. The
direct runner and the Prefect runner must invoke the same functions, validators,
provider factory, configuration, path conventions, and persistence layer.

The direct runner remains useful for simple local operation and testing. The
Prefect runner adds a web UI, execution history, retries, scheduling, remote
execution, concurrency control, asset lineage, and operational statistics.

## Intended data flow

```text
raw captures / inbox
        |
        v
validated short articles (ArticleShort)
        |
        v
extended articles (ArticleExtended)
        |
        +----------------------+----------------------+
        |                      |                      |
        v                      v                      v
image artifacts          audio artifacts        HTML previews
        |                      |                      |
        +----------------------+----------------------+
                               |
                               v
                    Anki package or publisher
```

The final publishing stage may initially write an `.apkg`. It may later update
an Anki instance or another destination without changing the article and media
stages.

## Code organization

A possible final organization is:

```text
src/vocabgen/pipeline/
    stages.py          # Normal Python stage functions
    manifest.py        # Artifact identity, checksums, and provenance
    runner.py          # Direct local runner

src/vocabgen/prefect/
    flows.py           # Thin @flow, @task, and asset wrappers

scripts/run_pipeline.py
scripts/run_pipeline_prefect.py
```

Prefect should be an optional dependency rather than a requirement for the
cleaner, preview command, or unit tests. Until the project has packaging extras,
it can live in a separate `requirements-prefect.txt` file.

## Stage boundaries

Useful task boundaries are operations that are slow, independently retryable,
or produce a durable artifact:

1. Safely clean and persist one inbox batch.
2. Generate and validate one extended article.
3. Generate the required images for one article.
4. Generate the required audio for one article.
5. Render one HTML preview.
6. Assemble and publish a deck.
7. Calculate and publish run statistics.

Tiny helper calls should remain ordinary functions. Making every sentence,
field, or file operation a task would add orchestration overhead and make the
UI difficult to understand.

## Idempotency and resumability

The project-owned artifact cache remains the source of truth. Prefect task
result caching is not a replacement for deterministic media paths or validated
JSON files.

Every durable stage should:

1. Calculate the expected artifact identity from its inputs.
2. Check whether a valid matching artifact already exists.
3. Skip completed work unless regeneration was requested.
4. Write to a temporary path.
5. Validate the temporary result.
6. Atomically publish the result.
7. Record its metadata and final status.

Retries are safe only when those rules hold. A retried task must not blindly
append duplicate Markdown, acknowledge an unpersisted inbox entry, or expose a
partial media file.

Provider-level retries and Prefect task retries serve different purposes but
must not multiply without a deliberate limit. Provider retries can handle a
short transient request failure. A Prefect retry can repeat an entire
idempotent stage after a broader task or infrastructure failure.

## Artifact identity and provenance

Prefect records run state and materialization history, but reproducible
provenance must be explicit. Each durable artifact should have metadata, either
in a shared manifest or a sidecar record, containing the relevant fields:

- Logical artifact identifier and stage.
- Schema or format version.
- Input artifact identifiers and checksums.
- Output checksum and path or storage URI.
- Provider and model name.
- Generation parameters and random seed where applicable.
- Prompt template identifier or checksum.
- Application version or Git revision when available.
- Creation time, validation status, and error summary.

The manifest makes artifacts understandable if the Prefect database is absent.
Prefect asset metadata should refer to the same information so that the UI can
show lineage and help diagnose a conversion problem.

Logical, location-independent asset keys are preferable to absolute paths. For
example:

```text
vocab://inbox/main
vocab://short/anorar
vocab://extended/anorar
vocab://image/anorar/root
vocab://audio/anorar/root
vocab://deck/spanish-vocabulary
```

Physical paths remain configuration. This avoids giving the same artifact a
different identity on the server and the laptop.

## UI and statistics

The Prefect UI should make both execution and data-product state visible. A run
summary can report:

- Inbox entries requested, accepted, skipped, and failed.
- Short and extended articles created or reused.
- Exact and fuzzy duplicate decisions.
- Images and audio files generated, reused, regenerated, and failed.
- Validation failures grouped by stage.
- Provider/model selection and task durations.
- Preview, deck, and publishing destinations.

Flow/task logs provide diagnostic detail. Prefect artifacts can provide a
short Markdown summary, tables, links to generated output, and progress for
long-running stages. Sensitive vocabulary text, credentials, and complete LLM
prompts should not be logged by default.

## Local and remote execution

A useful future topology is:

```text
                       Prefect UI and API
                    on an always-on server
                              |
              +---------------+---------------+
              |                               |
              v                               v
     CPU/API execution                  Mac execution
     always-on server                   available on demand
     - inbox processing                 - MPS image generation
     - remote LLM calls                 - local models
     - Markdown/JSON                    - optional local TTS
     - lightweight TTS
```

The always-on machine can host the Prefect server and persistent run database.
It can also execute stages that only need CPU, network APIs, or modest memory.
The Mac can run a Prefect worker or served flow connected to the same control
plane for stages that require MPS or locally installed models. GPU-dependent
work remains queued while that execution environment is unavailable.

If stages on different machines exchange artifacts, they need shared durable
storage such as an authenticated object store, a carefully configured shared
filesystem, or an explicit transfer step. Machine-local `cache/` directories
alone cannot support cross-machine dependencies.

The self-hosted Prefect UI and API should not be exposed directly to the public
internet without authentication and transport security. A private network or
VPN is preferable for a personal deployment.

## Ingestion endpoint

Remote capture should be a small application endpoint separate from the
Prefect UI. It should:

1. Authenticate the caller.
2. Validate and normalize the submitted snippet.
3. Atomically append it to `DraftInbox` or another durable queue.
4. Return a stable submission identifier.
5. Optionally trigger or schedule the appropriate Prefect deployment.

Keeping ingestion separate prevents the orchestration UI from becoming the
public application interface and allows the direct runner to process the same
queue.

## Resource control

Execution policy belongs in configuration:

- Remote LLM tasks use rate limits appropriate to their provider.
- Local LLM work respects available memory.
- Stable Diffusion normally has concurrency one per GPU/MPS device.
- TTS concurrency depends on its selected provider and machine.
- Deck assembly waits for all required validated media.

Prefect concurrency limits can protect APIs and shared resources. Local task
runners should also use an explicit worker count rather than an unbounded
default. Model initialization must be considered when selecting task
granularity: a task per image is undesirable if it reloads a large model for
every task. A per-article or per-modality worker that reuses the provider can be
more efficient.

## Prefect persistence

Prefect records flow and task states, logs, run history, assets, materialization
events, and artifacts in its backend. A lightweight self-hosted server can use
SQLite. A larger or highly concurrent deployment would need a more durable
server configuration.

Task return values are a separate concern. Prefect does not persist every task
result by default. When enabled, result persistence serializes Python return
values into configured storage; it does not take ownership of files written by
the vocabulary application. Project artifacts therefore remain explicit files
or objects with their own validation and manifests.

## Implementation sequence

### Phase 1: ordinary Python

- Complete the missing short-to-extended article stage.
- Define stable stage inputs and outputs.
- Make every durable write atomic and idempotent.
- Add artifact manifests and content-aware validation.
- Implement a direct end-to-end runner.
- Test interruption, retry, and partial-cache behavior without Prefect.

### Phase 2: optional Prefect wrapper

- Decorate only the established stage boundaries.
- Add retries, timeouts, task names, and explicit dependencies.
- Register stable logical assets and metadata.
- Publish progress and summary artifacts.
- Verify that direct and Prefect runners produce equivalent outputs.

### Phase 3: distributed personal deployment

- Run the control plane on the always-on server.
- Route CPU/API and MPS/model work to appropriate execution environments.
- Introduce shared artifact storage.
- Add the authenticated ingestion endpoint.
- Add publishing to the selected Anki destination.
- Add schedules or automations only where they provide concrete value.

## References

- [Prefect flows](https://docs.prefect.io/v3/concepts/flows)
- [Prefect tasks](https://docs.prefect.io/v3/concepts/tasks)
- [Prefect assets](https://docs.prefect.io/v3/concepts/assets)
- [Prefect artifacts](https://docs.prefect.io/v3/concepts/artifacts)
- [Prefect task runners](https://docs.prefect.io/v3/concepts/task-runners)
- [Prefect result persistence](https://docs.prefect.io/v3/advanced/results)
- [Self-hosted Prefect server](https://docs.prefect.io/v3/how-to-guides/self-hosted/server-cli)
