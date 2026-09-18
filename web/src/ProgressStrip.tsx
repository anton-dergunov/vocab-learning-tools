import type { Job, JobStep } from "./api";
import { isOpen } from "./jobs";

/**
 * One quiet line under an article's header, saying what the server is still doing to this word
 * (`docs/plans/processing-flow.md` §5). It shows work and never does it: the only thing it can ask
 * for is a new job, through Try again.
 *
 * It collapses when the job finishes. A failed step leaves one line until the owner dismisses it
 * or leaves the word.
 */

export interface StripLine {
  /** Each phase still ahead, in order; the one being worked on is `current`. */
  phases: { text: string; current: boolean }[];
  failure: string | null;
}

const PENDING = new Set(["pending", "running", "waiting"]);

function phase(step: JobStep): string | null {
  const waiting = step.state === "waiting" ? " (the provider is busy)" : "";
  switch (step.name) {
    case "clips":
      return `Finding recorded examples${waiting}`;
    case "pictures":
      if (step.total) {
        return `Drawing ${Math.min((step.done ?? 0) + 1, step.total)} of ${step.total}${waiting}`;
      }
      return `Drawing pictures${waiting}`;
    case "pronunciations":
      return `Recording audio${waiting}`;
    case "draw":
      return `Drawing${waiting}`;
    case "corpus.update":
      return `Updating recorded speech${waiting}`;
    case "anki.pull":
      return `Reading Anki's review state${waiting}`;
    case "brief":
      return `Writing picture briefs${waiting}`;
    /* A render is minutes of work in the companion container, and it reports a fraction as it goes —
       so this says how far along rather than only that it is going. `waiting` is deliberately not
       appended: this step waits because it is *following* a render, which is not a busy provider. */
    case "loop.render": {
      const fraction = typeof step.detail?.progress === "number" ? step.detail.progress : null;
      const doing = typeof step.detail?.doing === "string" ? step.detail.doing : "";
      if (doing) return fraction === null ? doing : `${doing} · ${Math.round(fraction * 100)}%`;
      return fraction === null ? "Making the loop" : `Making the loop · ${Math.round(fraction * 100)}%`;
    }
    case "loop.store":
      return "Storing the track";
    case "capture": {
      const words = Array.isArray(step.detail?.words) ? step.detail.words.length : 0;
      return `Reading the text${words ? ` · ${words} so far` : ""}${waiting}`;
    }
    default:
      return null;
  }
}

function failureOf(step: JobStep): string {
  switch (step.name) {
    case "clips":
      return "Couldn't search recorded speech";
    case "pictures": {
      const refused = Number(step.detail?.refused ?? 0);
      if (step.total && refused) return `${step.total - refused} of ${step.total} pictures drawn`;
      return "The pictures could not be drawn";
    }
    case "pronunciations":
      return "Some audio could not be recorded";
    /* Lead with what happened and then say why. The `default` branch below already prefers
       `step.message`; returning a constant here threw away the one sentence that names the cause —
       which is how a render that died on a missing sample pack read as "could not be made". */
    case "loop.render":
      return step.message ? `The loop could not be made — ${step.message}` : "The loop could not be made";
    case "loop.store":
      return step.message
        ? `The loop was made but its track could not be stored — ${step.message}`
        : "The loop was made but its track could not be stored";
    case "corpus.update":
      return "The recorded-speech corpus could not be updated";
    default:
      return step.message || "Something could not be finished";
  }
}

/** What the strip says for a job, or null when it should not be there at all. */
export function stripOf(job: Job | undefined): StripLine | null {
  if (!job || job.state === "cancelled" || job.state === "done") return null;
  if (isOpen(job)) {
    const phases = job.steps
      .filter((step) => PENDING.has(step.state))
      .map((step) => ({ text: phase(step), current: step.state !== "pending" }))
      .filter((entry): entry is { text: string; current: boolean } => entry.text !== null);
    if (!phases.length) return { phases: [{ text: "Waiting to start", current: false }], failure: null };
    return { phases, failure: null };
  }
  const failed = job.steps.find((step) => step.state === "failed");
  if (failed) return { phases: [], failure: failureOf(failed) };
  return { phases: [], failure: job.error === "interrupted"
    ? "Interrupted when the server restarted"
    : job.message || "Something could not be finished" };
}

export default function ProgressStrip({ job, onRetry, onDismiss }: {
  job: Job | undefined;
  onRetry(): void;
  onDismiss(): void;
}) {
  const line = stripOf(job);
  if (!line) return null;
  if (line.failure) {
    return <div className="progress-strip failed" role="status">
      <span>{line.failure}</span>
      <span className="sep">·</span>
      <button type="button" className="strip-action" onClick={onRetry}>Try again</button>
      <button type="button" className="strip-dismiss" aria-label="Dismiss" onClick={onDismiss}>×</button>
    </div>;
  }
  return <div className="progress-strip" role="status" aria-live="polite">
    {line.phases.map((entry, index) => <span key={entry.text}>
      {index > 0 && <span className="sep">·</span>}
      <span className={entry.current ? "now" : undefined}>{entry.text}</span>
    </span>)}
  </div>;
}
