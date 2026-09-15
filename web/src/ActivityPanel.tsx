/**
 * What is being made, what is still missing, and what was made lately.
 *
 * Three of those four sections come from the **graph**, and that is the correction that matters. The
 * panel used to end in a session-scoped log of what this device had drawn, which was wrong twice
 * over: it emptied on every reload, so five pictures read as two, and it could never mention a
 * picture the server's sweep drew while nobody was looking. Everything a record can answer is now
 * read from the record, so it survives a restart and covers both engines.
 *
 * What is left to the engine is the one thing no record holds: the unit in flight on *this* device,
 * and the failures that produced no row at all — a rate limit or an unreachable server leaves
 * nothing behind, so if this does not say so, nothing does.
 *
 * Built for what comes next as much as for pictures: audio is a second `kind` on the same job and a
 * second row in the same tables, not a second panel.
 */

import { PictureIcon } from "./icons";
import { relativeTime } from "./format";
import { enrichment } from "./enrichment";
import type { EnrichmentStatus, EnrichmentWait } from "./enrichment";
import type { ImageWork, ImageWorkEntry } from "./selectors";

/** Present tense while it is happening. The finished lists use the record, and read as facts. */
const DOING: Record<string, string> = {
  brief: "describing the senses",
  render: "drawing",
  clips: "looking for clips",
  pronounce: "recording pronunciations"
};

const SHOWN = 12;

/** The topbar indicator. Quiet by design: nothing here is a fault, and none of it is urgent. */
export function ActivityChip({ status, outstanding, onOpen }: {
  status: EnrichmentStatus; outstanding: number; onOpen(): void;
}) {
  // Shown only when there is something to say. An always-present chip reading "nothing happening"
  // is a permanent piece of furniture that earns nothing.
  if (!status.active && !status.waiting.length && !outstanding) return null;
  const label = status.active
    ? `Making pictures: ${status.active.label}`
    : outstanding
      ? `${outstanding} senses still have no picture`
      : "Pictures queued";
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

function name(entry: ImageWorkEntry): string {
  return `${entry.headword} · sense ${entry.senseNumber}`;
}

export function ActivityPanel({ status, work, onClose }: {
  status: EnrichmentStatus; work: ImageWork; onClose(): void;
}) {
  const now = Date.now();
  const outstanding = work.unbriefed.length + work.undrawn.length;
  // Only the failures. A success is a picture in the article and a failure that reached the server
  // is a row with a reason; what is left for a session list is the attempt that produced neither.
  const lost = status.recent.filter((job) => job.error);

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
                <span>{DOING[status.active.phase] ?? status.active.phase}</span>
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
          {status.waiting.length > 0 && <p className="config-help">
            {status.waiting.length} queued behind it: {waitingLabels(status.waiting)}.
            {/* The queue is sequential, so one slow word holds up every one behind it, and until
                now the only way out was to sign out. The call in flight is left alone — it is the
                server's and finishes either way — and nothing is lost by dropping the rest: a word
                without its picture is missing in the graph, which is where the counts below come
                from and what the server's own sweep reads. */}
            <button className="link-btn" onClick={() => enrichment.clearWaiting()}>
              Clear the queue
            </button>
          </p>}
        </section>

        <section className="config-section">
          <h3>Where your vocabulary stands</h3>
          <p className="config-help">
            Counted from your own words rather than from a list of jobs, so this is what is actually
            missing — and it falls as the server works through it, whether or not this device is
            doing anything.
          </p>
          <div className="activity-stats">
            <Stat label="Have a picture" value={work.drawn.length} />
            <Stat label="Waiting" value={outstanding} />
            <Stat label="Could not be drawn" value={work.failed.length} />
            <Stat label="Set to have none" value={work.suppressed.length} />
          </div>
        </section>

        {work.failed.length > 0 && <section className="config-section">
          <h3>Could not be drawn</h3>
          <p className="config-help">
            The provider’s own words. A different description often passes where one did not — open
            the sense and edit it.
          </p>
          <ul className="activity-list">
            {work.failed.slice(0, SHOWN).map((entry) => <li key={entry.prompt.id} className="failed">
              <strong>{name(entry)}</strong>
              <span className="activity-time">{relativeTime(entry.prompt.editedAt)}</span>
              <span className="activity-error">{entry.prompt.failureReason ?? "no reason given"}</span>
            </li>)}
          </ul>
        </section>}

        {work.drawn.length > 0 && <section className="config-section">
          <h3>Drawn recently</h3>
          <p className="config-help">
            Newest first, from the records themselves — so a picture the server drew overnight is
            here too, and so is one from before this app was last opened.
          </p>
          <ul className="activity-list">
            {work.drawn.slice(0, SHOWN).map((entry) => <li key={entry.prompt.id}>
              <strong>{name(entry)}</strong>
              {/* A picture the owner attached has no style and no model that drew it, so it says
                  so once rather than reporting the style of some earlier drawn version. */}
              {entry.prompt.imageModelId
                ? <><span>{entry.prompt.styleId}</span><span>{entry.prompt.imageModelId}</span></>
                : <span>your own picture</span>}
              <span className="activity-time">{relativeTime(entry.prompt.editedAt)}</span>
            </li>)}
          </ul>
          {work.drawn.length > SHOWN && <p className="config-help">
            …and {work.drawn.length - SHOWN} more.
          </p>}
        </section>}

        {lost.length > 0 && <section className="config-section">
          <h3>Went wrong on this device</h3>
          <p className="config-help">
            This session only, and only the attempts that left no record — a provider that was busy
            or a server that could not be reached. Anything the server did record is above.
          </p>
          <ul className="activity-list">
            {lost.map((job) => <li key={job.id} className="failed">
              <strong>{job.label}</strong>
              <span>{DOING[job.phase] ?? job.phase}</span>
              <span className="activity-error">{job.error}</span>
            </li>)}
          </ul>
        </section>}
      </div>
    </section>
  </div>;
}

/** The words, not the units: two senses of one word waiting is "la salchicha", once. */
function waitingLabels(waiting: EnrichmentWait[]): string {
  const words = [...new Set(waiting.map((item) => item.label).filter(Boolean))];
  return words.slice(0, 4).join(", ") + (words.length > 4 ? ` and ${words.length - 4} more` : "");
}

function Stat({ label, value }: { label: string; value: number }) {
  return <div className="stat">
    <div className="label">{label}</div>
    <div className="v">{value}</div>
  </div>;
}
