# Round 4 · 2026-09-05 · throughput

Round 4 is 100 senses, and while it ran the question became *how long would all of them take*. That
turned into a measurement, and the answer changed the architecture.

## The ceiling is one image per minute, per model

39 minutes of a live run, 41 images, gaps between consecutive images:

| Gap | Count |
|---|---:|
| < 5 s | 1 |
| 5–20 s | 0 |
| 20–45 s | 3 |
| 45–90 s | **36** |
| > 90 s | 0 |

Median **60.5 s**. Sustained **1.02 images/min**.

It is a refill rate, not a concurrency limit, and not our own pacing:

- A 429 comes back in **0.1–1.3 s**. A queue would make us wait; an empty bucket refuses instantly.
- Serial, one request at a time, no concurrency at all: the first call succeeded, the next four were
  refused instantly.
- Six concurrent calls: exactly one succeeded.

So worker count, rate-limit settings and cooldown tuning cannot move it. **We were already at the
ceiling** — 1.02 against a limit of about 1.

## What is not available

- **Regional sharding.** `us-central1` and `europe-west4` both return 404 for these models: the
  image models are global-only, so there is no second region to spread across.
- **More workers.** Three workers against a 1/min bucket means two of them are always being refused.

## What is available

**Each model has its own bucket.** `gemini-3.1-flash-image` answered while
`gemini-3.1-flash-lite-image` was saturated by the running job, and its own burst behaved exactly
like flash-lite's — one through, the rest refused. Two models therefore run at twice the rate.

The runner now takes a list of image models, gives each its own gate, and hands a job whichever is
free soonest. A quota pause applies to the model that hit it, not to the pool.

| Models | Rate | 2,288 senses | Cost |
|---|---:|---:|---:|
| flash-lite only | ~1.0/min | **38 h** | $77 |
| + flash | ~2.0/min | **19 h** | $115 |
| + pro | ~3.0/min | **13 h** | $217 |

Pro is four times the price of flash-lite, slower per image, and ranked below both Flash variants in
the finalist benchmark, so it is a throughput purchase and nothing else.

**Decided: Flash Lite alone.** The second model halves the clock and adds $38, and the budget is the
binding constraint rather than the schedule — 38 hours of unattended background running is
affordable in a way that doubling the bill is not. The pool stays in the code and `--image-models`
turns it on, so the decision is one flag away if the credits turn out to have room.

**The quota increase is still the real fix**, and it is free. Everything above is a workaround for a
default limit that a request in the Cloud console could lift by an order of magnitude. Ask first;
run two models meanwhile.
