# The NAS → MacBook job queue

**Status:** A sketch, deliberately, and kept on purpose. Nothing waits on it, and it should not be
built until something concretely needs it — but local models are a real possibility
([`provider-management.md`](provider-management.md)), and some of them only run well on the Mac.

**The job record it asked for now exists**: a `jobs` table beside `sync_state`, owner-scoped and
never replicated, with a runner inside the server ([`../server.md`](../server.md), "Jobs"). So the
question this plan once declined to answer — *where does the record of outstanding work live* — has
an answer, and it is not a queue a phone would carry. What is still only a sketch is the rest: a
second machine doing the work.

The provider roadmap this began as plan 07 of is finished — one catalogue, one
`src/acervo/models/` package, one place in Settings where the owner chooses. The provider surface a
remote worker would call therefore exists; this is kept because the asymmetry it describes has not
gone away, not because there is a plan queued behind it.

## Outcome

A written answer to one awkward asymmetry, and an honest statement of why it is not being built yet.

The asymmetry: **the machine that is always on has no GPU, and the machine with the GPU is not always
on.** Acervo runs 24/7 on a Synology NAS, which can serve, sync, hold dictionaries and call hosted
APIs, but cannot run a diffusion model. The MacBook has unified memory and MLX and runs local models
well, and is closed for most of the day.

## Current state

Nothing queues anything. Every generation path is a foreground command run by a person:

- `scripts/generate_images.py run` — a laptop run, because that is where the prompt work happened;
  the server's own runner draws every newly saved word with hosted providers
- `experiments/image_benchmark/benchmark_image_models.py` — a research harness, one subprocess per job
- `acervo-worker` — a one-shot container, `profiles: ["tools"]`, no ports, started by
  `docker compose run --rm` to do one job and exit

The pieces a queue would need mostly exist already, which is part of why building it now would be
premature — it would look easy and then not be:

- **A store that is already a queue.** `jobs/images/run.py`'s `Store` is filesystem-as-state:
  `records/`, `images/`, `briefs/`, `refusals/`. `plan()` computes what is missing, which is
  the only queue read anything needs. A sweep is already idempotent and already resumable.
- **Idle gating, already specified.** `docs/image-generation-research.md:186-215` sets out the rules
  for a macOS background worker in detail — five minutes of input idle, on AC power, thermal and
  memory nominal, no microphone or camera in use, one image per child process, fail closed — against
  `tools/macos_idle_probe.swift`.
- **Subprocess isolation, already built.** `experiments/image_benchmark/image_benchmark_runner.py`'s contract
  (`contract_version: 1`, JSON request in, JSON result out, SDKs imported inside the backend
  function) is exactly the shape a remote worker would claim work in, and it already records peak
  memory per job.
- **Measured local cost.** MFLUX FLUX.2 Klein Q4: 2.5 GiB RSS, 5.65 GiB MLX peak, 49 seconds an
  image. Sana Sprint: 8–10 GiB RSS, judged too heavy. LCM DreamShaper: about 4.6 GiB, best local
  appeal at 4.56 but three rejections in twelve.

## Decisions

### It is not built yet, and the reason is that nothing needs it

The research the queue would exist to serve concluded **against** a local default. The chosen
hierarchy in `docs/image-generation-research.md:6-25` runs emoji, icon scene, Cloudflare FLUX.2 Klein,
then Gemini Flash Lite for the bulk import — and no local diffusion. The finalist scores support that:
the best local candidate reached 3.81 against Cloudflare's 4.54, and the cheapest hosted option costs
nothing inside a daily allocation that stops rather than bills.

So a queue built today would carry work that a free hosted API does better. Building it would be
speculative abstraction, which this roadmap's pragmatism rule forbids.

### What would change that — write the trigger down, so it is recognised

Build this when one of these is true, and not before:

1. **A local model becomes genuinely better for a job**, not merely cheaper. A voice for plain
   pronunciation is the likeliest candidate: it runs thousands of times, needs no quality ceiling,
   and Kokoro was small — though `src/acervo/tts/` has since been deleted, so a local voice is a
   rebuild rather than a revival. [`provider-management.md`](provider-management.md) is
   where that question is asked: if a local voice runs on the NAS, no queue is needed; if it needs
   the Mac, this is the plan.
2. **Hosted providers stop being acceptable** — a privacy requirement, a price change, or every free
   allocation exhausted at once.
3. **A job is too large for a foreground command.** The Vertex bulk import was 2,000 images run by
   hand. A second sweep of that size, wanted while nobody is watching, is a reason.
4. **The owner wants generation from the interface**, on the phone, with no laptop involved. This is
   the one most likely to arrive first, and note that it does *not* need a Mac: hosted providers in
   `acervo-worker` already satisfy it. Do not let this trigger pull in the GPU machinery.

### If it is built: the direction, not the design

Enough to start from, deliberately not enough to implement without thinking.

**A job is a record, not a message** — and the record now exists. The server's `jobs` table already
holds every piece of outstanding work; a separate broker — Redis, a queue service, anything with its
own uptime — would be a second source of truth about it. A Mac job would be a row there with a kind
the server's runner skips, naming what to make, for which sense, with which chain, and carrying a
claim.

**The worker claims, it is not assigned.** The NAS does not know when the Mac is awake, so pushing is
wrong. The Mac polls: claim the oldest unclaimed job by writing its own device id and a lease, do it,
post the result, release. A lease that expires is reclaimable, which is the whole of the failure
handling — a Mac that closes mid-job loses one job, and the sweep is already idempotent.

**It is the same pipeline, on a different machine.** Not new code: the laptop image run already
exists, and a claiming loop is a wrapper around it, reaching the jobs through a route with
`client.py` the way every batch tool reaches the graph. It runs
on the Mac under a LaunchAgent, gated by the rules already specified at
`image-generation-research.md:186-215`, and it must fail closed — no AC power, no work.

**Writes stay online-only and synchronous.** A queue is not a write buffer. It queues *generation*,
which is work that produces a record; it never queues a vocabulary write, because
"a write without the server must fail visibly and change nothing locally; never queue it" is a data
rule and this does not get to bend it.

### What must not happen

- **No new compose service.** `acervo-worker` is one-shot by design. A claiming loop is a subcommand
  with a `--watch` flag, run under a LaunchAgent on the Mac, not a daemon in the compose file.
- **No second pipeline.** A queued image is generated by the same `models.image()` and written
  through the same store as a foreground one. If the queue needs its own generation path, the design
  is wrong.
- **No third provider mechanism.** A local model reached by this queue is a catalogue row whose
  transport happens to be "spawn a subprocess on the machine that claimed the job".

## Implementation work

None. This plan is a sketch by decision.

If a trigger fires, the first step is not code — it is to come back to this document, name which
trigger fired, and turn the direction above into an `## Implementation work` section with a record
shape, a claim protocol and a lease duration. Then implement that.

## Public interfaces and data

Not designed. The shape to start from is a row in the existing `jobs` table — kind, subject, the
chain to use — plus the two fields a claim needs: who holds it and until when. The question this
section used to leave open, whether a job record would replicate to every phone, is answered: jobs
are server state and never replicate, so a claiming worker reads them through a route.

## Acceptance tests and verification

Not applicable — nothing is built.

When it is, the verification that matters is not a unit test:

```bash
# the only scenario worth proving, and it takes a day rather than a test run
#  · queue 50 jobs on the NAS with the MacBook closed
#  · nothing is claimed, nothing is lost, and the NAS is undisturbed
#  · open the MacBook, on AC power, and walk away
#  · work is claimed only after the idle threshold, and stops the moment you touch the keyboard
#  · close the lid mid-job: exactly one job's lease expires and is reclaimed, none are duplicated
#  · unplug the power: work stops, and it fails closed rather than draining the battery
#  · the finished records are indistinguishable from ones generated in the foreground
```

## Non-goals

- **No broker, no message queue, no Celery, no Redis.** The `jobs` table is the state. Adding a broker to a two-machine household is not warranted.
- **No queueing of vocabulary writes.** Writes are online-only and synchronous, by data rule.
- **No priority, no scheduling policy, no retry state machine.** Oldest unclaimed job first. If that
  is ever not enough, it will be obvious.
- **No cross-machine model cache sharing.** The Mac keeps its own weights.
- **No Windows or Linux worker.** One GPU machine exists.
- **No attempt to make the NAS run a GPU model.** It has no GPU. That is the premise, not a problem
  to solve.
