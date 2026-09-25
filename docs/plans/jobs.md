# Jobs · open questions

**Status:** open, none blocking. The runner as built is [`../architecture/jobs.md`](../architecture/jobs.md).

- **Parallel lanes.** The runner runs one job at a time, because the allowances are the owner's own; a
  resting job gives up its turn, but two jobs never run side by side. Per-kind lanes — so a slow image
  provider does not hold up clip searches — are the natural next step if waiting becomes noticeable.
- **The event stream through the macOS host.** Whether a long-lived streamed response passes through the
  host's web view and Tailscale Serve without being buffered has not been checked. The 60-second pull is
  the fallback either way, so a failure costs latency, not correctness.
- **Whose nightly run updates the corpus.** Schedule settings are per owner and `corpus.update` runs from
  each owner's nightly job, but the corpus is shared by the whole deployment. A second account would
  update it a second time every night. Decide whether the corpus step belongs to one owner or to the
  deployment before there is a second account.
- **A second machine**, and **Prefect** as an orchestrator, are
  [`nas-to-mac-job-queue.md`](nas-to-mac-job-queue.md) and the Prefect section of the runner's design.
