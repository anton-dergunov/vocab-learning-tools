/**
 * What is being made, and what is still missing.
 *
 * Two halves, and they answer different questions from different places.
 *
 * **In flight** is this device's own work — the word you just saved, whose pictures are being drawn
 * one at a time behind the article. `enrichment.ts` knows it precisely because it is doing it.
 *
 * **Outstanding** is a query against the replica (`selectors.imageWork`), which is how work the
 * *server's* sweep is doing becomes visible without any job store to poll. There deliberately is
 * not one: an owner-scoped job record would replicate to every device, so a phone would carry a
 * queue of work it could never do — the question `docs/plans/nas-to-mac-job-queue.md` declined to
 * answer, and this is how it stays unasked. The number simply falls as the server works, on each
 * sync pull.
 *
 * Built for what comes next as much as for pictures: audio is a second `kind` on the same job and a
 * second row in the same table, not a second panel.
 */

import { PictureIcon } from "./icons";
import { relativeTime } from "./format";
import type { EnrichmentStatus } from "./enrichment";
import type { ImageWork } from "./selectors";

const PHASE: Record<string, string> = {
  brief: "describing the senses",
  render: "drawing"
};

/** The topbar indicator. Quiet by design: nothing here is a fault, and none of it is urgent. */
export function ActivityChip({ status, outstanding, onOpen }: {
  status: EnrichmentStatus; outstanding: number; onOpen(): void;
}) {
  // Shown only when there is something to say. An always-present chip reading "nothing happening"
  // is a permanent piece of furniture that earns nothing.
  if (!status.active && !status.waiting && !outstanding && !status.recent.length) return null;
  const label = status.active
    ? `Making pictures: ${status.active.label}`
    : outstanding
      ? `${outstanding} senses still have no picture`
      : "Recent picture work";
  return <button
    className={`tb-btn activity-chip${status.active ? " working" : ""}`}
    onClick={onOpen}
    aria-label={label}
    title={label}
  >
    <PictureIcon />
    {outstanding > 0 && <span className="activity-count">{outstanding}</span>}
  </button>;
}

function elapsed(from: number, to: number): string {
  const seconds = Math.max(0, Math.round((to - from) / 1000));
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

export function ActivityPanel({ status, work, onClose }: {
  status: EnrichmentStatus; work: ImageWork; onClose(): void;
}) {
  const now = Date.now();
  const outstanding = work.unbriefed.length + work.undrawn.length;

  return <div className="modal-backdrop" role="presentation"
    onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="settings" role="dialog" aria-modal="true" aria-labelledby="activity-title">
      <header>
        <h2 id="activity-title">Making pictures</h2>
        <button className="close" onClick={onClose} aria-label="Close">×</button>
      </header>

      <div className="settings-body">
        <section className="config-section">
          <h3>Right now</h3>
          {status.active
            ? <div className="activity-row" role="status">
                <strong>{status.active.label}</strong>
                <span>{PHASE[status.active.phase] ?? status.active.phase}</span>
                <span className="activity-time">{elapsed(status.active.startedAt, now)}</span>
              </div>
            : status.restingUntil
              // Not a failure and not worth an alarm: providers meter roughly one picture a minute,
              // so waiting is the normal way to draw a lot of them.
              ? <p className="config-help" role="status">
                  Waiting for the picture provider’s allowance to come back
                  ({elapsed(now, status.restingUntil)}).
                </p>
              : <p className="config-help">Nothing is being drawn on this device.</p>}
          {status.waiting > 0 && <p className="config-help">
            {status.waiting} more {status.waiting === 1 ? "word" : "words"} queued behind it.
          </p>}
        </section>

        <section className="config-section">
          <h3>Still to do</h3>
          <p className="config-help">
            Counted from your own vocabulary rather than from a list of jobs, so this is what is
            actually missing — and it falls as the server works through it, whether or not this
            device is doing anything.
          </p>
          <div className="activity-stats">
            <Stat label="Have a picture" value={work.ready} />
            <Stat label="Waiting" value={outstanding} />
            <Stat label="Could not be drawn" value={work.failed.length} />
            <Stat label="Set to have none" value={work.suppressed.length} />
          </div>
        </section>

        {status.recent.length > 0 && <section className="config-section">
          <h3>Just finished</h3>
          <p className="config-help">
            This session only. What happened while you were away is not a log — it is a sense with
            a picture, or one that says why it has none.
          </p>
          <ul className="activity-list">
            {status.recent.map((job) => <li key={job.id} className={job.error ? "failed" : ""}>
              <strong>{job.label}</strong>
              <span>{PHASE[job.phase] ?? job.phase}</span>
              {job.finishedAt && <span className="activity-time">
                {elapsed(job.startedAt, job.finishedAt)} · {relativeTime(new Date(job.finishedAt).toISOString())}
              </span>}
              {job.error && <span className="activity-error">{job.error}</span>}
            </li>)}
          </ul>
        </section>}
      </div>
    </section>
  </div>;
}

function Stat({ label, value }: { label: string; value: number }) {
  return <div className="stat">
    <div className="label">{label}</div>
    <div className="v">{value}</div>
  </div>;
}
