/**
 * The client's half of drawing pictures: one unit of work at a time, and a status to watch it by.
 *
 * Shaped the way `sync.ts` owns the sync schedule and status, and for the same reason — the engine
 * owns *when*, the caller owns *what*. Read through `useSyncExternalStore`, like `SyncStatus`.
 *
 * **This is the foreground engine, not the only one.** It enriches the word you just saved, because
 * you are looking at it and a picture in a minute beats a picture in five. Everything else — words
 * the ingest script added, the backlog, anything that failed while nobody was watching — belongs to
 * `acervo-worker images sweep`, which runs on the server on a timer and which this engine
 * deliberately does not duplicate. The two need no coordination at all: an image prompt's id is
 * derived from its sense id, so both converge on the same row, and whichever arrives second finds
 * the work already done or is refused as stale.
 *
 * Nothing here is persisted and nothing here is a queue in the graph. What is *outstanding* is a
 * query against the replica (`selectors.imageWork`); what is in flight is this session's own
 * business and is gone when the tab closes — at which point the sweep finishes the word. An
 * owner-scoped job record would replicate to every device, which is the question
 * `docs/plans/nas-to-mac-job-queue.md` declined to answer, and this is how it stays unasked.
 */

import { AcervoApiError, backendSession, type ImagePromptRow } from "./api";
import { forget } from "./media";
import { repository } from "./repository";
import { syncEngine } from "./sync";

/** Audio is the next `kind`, not the next engine — clips were the third and went in here. */
export type EnrichmentKind = "image" | "clip" | "audio";
export type EnrichmentPhase = "brief" | "render" | "clips";

export interface EnrichmentJob {
  id: string;
  kind: EnrichmentKind;
  lexemeId: string;
  /** Which sense is being drawn. Null during the brief, which covers all of them at once. */
  senseId: string | null;
  /** The headword, captured when queued: the replica may have moved on by the time it is shown. */
  label: string;
  phase: EnrichmentPhase;
  startedAt: number;
  finishedAt?: number;
  /** Set when the unit failed. The provider's words where there are any. */
  error?: string;
}

/** One thing waiting its turn — enough of it for a picture to show that it is coming. */
export interface EnrichmentWait {
  lexemeId: string;
  /** Null for a whole word: every sense of it is waiting. */
  senseId: string | null;
  label: string;
}

export interface EnrichmentStatus {
  /** The unit being worked on right now, or nothing. Strictly one at a time. */
  active: EnrichmentJob | null;
  /** What is queued behind it, in order. A picture reads this so that pressing Draw while
   *  something else is drawing still shows on the picture rather than looking ignored. */
  waiting: EnrichmentWait[];
  /** This session's outcomes, newest first, capped — a view of recent work, not a log. */
  recent: EnrichmentJob[];
  /** Set while the engine is waiting out a provider's rate limit rather than working. */
  restingUntil: number | null;
  running: boolean;
}

const RECENT = 20;
/** Providers meter roughly one image a minute, so a refusal means waiting, not trying harder. */
const FIRST_REST = 30_000;
const LONGEST_REST = 10 * 60_000;
/** A 429 does not say whether a per-minute or a per-day allowance ran out, so the rest doubles. */
const RETRY_CODES = new Set(["llm_rate_limited", "llm_unavailable", "llm_unreachable"]);

const EMPTY: EnrichmentStatus = {
  active: null, waiting: [], recent: [], restingUntil: null, running: false
};

/**
 * A unit of work. A **word** is "give this everything it lacks" and covers a brief and any number
 * of renders; a **picture** is one render the owner asked for by hand, carrying the brief and style
 * they typed.
 *
 * Both go through the one queue rather than a redraw firing straight at the route, and that is the
 * point: providers meter roughly one picture a minute, so two at once buys a 429 rather than a
 * second picture — and a hand-asked redraw shows up in the activity panel exactly like the rest.
 */
type Unit =
  | { kind: "word"; lexemeId: string; label: string }
  | {
      kind: "picture";
      lexemeId: string;
      senseId: string;
      promptId: string;
      label: string;
      prompt?: string;
      styleId?: string;
    };

class EnrichmentEngine {
  private status: EnrichmentStatus = EMPTY;
  private listeners = new Set<() => void>();
  private queue: Unit[] = [];
  /**
   * The unit being worked on, which is *not* the same as `status.active`.
   *
   * `status.active` is for display and is set once a model call actually begins; a word spends a
   * moment before that asking whether drawing is switched on at all. Deduping against the display
   * state let a second `enqueue` slip into that window and brief the same word twice.
   */
  private current: Unit | null = null;
  private working: Promise<void> | null = null;
  /**
   * Per kind, not one shared timer.
   *
   * A picture is an image call metered by an image provider at roughly one a minute; a clip search
   * is a text call metered somewhere else entirely. Sharing one backoff means an image 429 silences
   * clip search for ten minutes for no reason — exactly the wrong shape when the owner is watching
   * the article they just saved. The brief rides with the pictures despite being a text call,
   * because a word whose brief is rate-limited has nothing to draw either way.
   */
  private rest: Record<EnrichmentKind, number> = { image: FIRST_REST, clip: FIRST_REST, audio: FIRST_REST };
  private stopped = false;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  getStatus = (): EnrichmentStatus => this.status;

  /**
   * Ask for this word's pictures. Returns immediately; the work happens behind the status.
   *
   * Idempotent by construction: a word already queued is not queued twice, and a word whose senses
   * all have pictures costs one query and no call. Nothing checks whether the *server* is also
   * working on it, because the derived id makes that harmless.
   */
  enqueue(lexemeId: string, label: string): void {
    if (this.stopped) return;
    const asked = (item: Unit | null) => item?.kind === "word" && item.lexemeId === lexemeId;
    if (asked(this.current) || this.queue.some(asked)) return;
    this.push({ kind: "word", lexemeId, label });
  }

  /**
   * Draw one picture the owner asked for, with the brief and style they typed.
   *
   * Deliberately not awaited by the caller: the dialog closes and the picture itself says it is
   * being redrawn, which is the difference between a button that reacts and one that hangs for
   * forty seconds. It joins the same queue as everything else, so it cannot race the automatic
   * work against a provider that allows one picture a minute.
   */
  redraw(unit: { lexemeId: string; senseId: string; promptId: string; label: string;
                 prompt?: string; styleId?: string }): void {
    if (this.stopped) return;
    // Deduped only against an *identical* request already queued — same picture, same words. A
    // second press with a changed brief is a second intention and is honoured, because the dialog
    // closes on Draw: pressing again means reopening it and typing, which nobody does by accident.
    // Dropping that silently would be a worse failure than drawing one picture twice.
    const identical = (item: Unit) =>
      item.kind === "picture"
      && item.promptId === unit.promptId
      && item.prompt === unit.prompt
      && item.styleId === unit.styleId;
    if (this.queue.some(identical)) return;
    this.push({ kind: "picture", ...unit });
  }

  private push(unit: Unit): void {
    this.queue.push(unit);
    this.update({ waiting: this.waits() });
    void this.run();
  }

  private waits(): EnrichmentWait[] {
    return this.queue.map((item) => ({
      lexemeId: item.lexemeId,
      senseId: item.kind === "picture" ? item.senseId : null,
      label: item.label
    }));
  }

  /**
   * Drop everything waiting, and leave the one in flight alone.
   *
   * The queue is strictly sequential, so a single slow unit holds up every word behind it — and
   * until now there was no way to say "stop bothering with the rest" short of signing out. The call
   * in flight is deliberately not cancelled: it is the server's, it finishes and writes either way,
   * and abandoning it would throw away work already paid for.
   *
   * Nothing is lost by clearing. A word whose picture is still missing is missing in the *graph*,
   * which is what the sweep reads and what the counts below are drawn from — the queue is only this
   * device's intention to get to it sooner.
   */
  clearWaiting(): void {
    this.queue = [];
    this.update({ waiting: [] });
  }

  /** Stop after the unit in flight. Used when signing out — never mid-call, which would waste it. */
  stop(): void {
    this.stopped = true;
    this.queue = [];
    this.current = null;
    this.update({ waiting: [] });
  }

  resume(): void {
    this.stopped = false;
  }

  private update(changes: Partial<EnrichmentStatus>): void {
    this.status = { ...this.status, ...changes };
    this.listeners.forEach((listener) => listener());
  }

  private finish(job: EnrichmentJob, error?: string): void {
    const done = { ...job, finishedAt: Date.now(), error };
    this.update({
      active: null,
      recent: [done, ...this.status.recent].slice(0, RECENT)
    });
  }

  private run(): Promise<void> {
    if (this.working) return this.working;
    this.working = this.drain().finally(() => {
      this.working = null;
      this.update({ running: false, active: null, waiting: this.waits() });
    });
    this.update({ running: true });
    return this.working;
  }

  private async drain(): Promise<void> {
    while (!this.stopped) {
      const next = this.queue.shift();
      if (!next) return;
      this.current = next;
      this.update({ waiting: this.waits() });
      try {
        if (next.kind === "word") {
          // Each kind asks its own switch, inside. Gating the whole unit on `drawEnabled` meant
          // turning pictures off also turned clip search off, which is two decisions wearing one
          // control — and the settings screens are deliberately separate.
          await this.word(next.lexemeId, next.label);
        } else {
          // A redraw is deliberately not gated. You pressed the button; switching automatic
          // drawing off is how you get a word with no pictures and then add the one you want.
          await this.picture(next);
        }
      } finally {
        this.current = null;
      }
    }
  }

  /**
   * Whether the owner wants pictures drawn on their own, asked of the server each time.
   *
   * Not cached, and asked here rather than trusted from a copy this module keeps: the setting is
   * owner state on the server, and a stale copy would either draw for someone who had switched it
   * off — which is the bug this fixes — or refuse to draw for someone who never opened Settings.
   * It is one indexed read against a local SQLite file, set against a model call.
   *
   * Unreachable means no: nothing can be drawn without the server anyway, so a failure here costs
   * only the *decision*, and the sweep will pick the word up later regardless.
   */
  private async drawingIsOn(): Promise<boolean> {
    try {
      return (await backendSession.imageSettings()).drawEnabled;
    } catch {
      return false;
    }
  }

  /**
   * Whether the owner wants the corpus consulted on its own, asked of the server each time.
   *
   * The same argument as `drawingIsOn`, and unreachable means no for the same reason: nothing can
   * be searched without the server anyway, so a failure here costs only the decision.
   */
  private async searchIsOn(): Promise<boolean> {
    try {
      return (await backendSession.clipSettings()).searchEnabled;
    } catch {
      return false;
    }
  }

  /**
   * Whether this word has ever been through a clip search, read from the replica.
   *
   * `clipsSearchedAt` answers it on its own: null is never consulted, and set means consulted —
   * including consulted and nothing was good enough, which is the common answer and must not send
   * anyone back for a second look. The search is one-shot at save; nothing re-searches.
   */
  private needsClips(lexemeId: string): boolean {
    const lexeme = repository.snapshot().lexemes.find((record) => record.id === lexemeId);
    return Boolean(lexeme) && !lexeme!.deleted && lexeme!.clipsSearchedAt === null;
  }

  /** One picture the owner asked for, drawn with whatever they typed. */
  private async picture(unit: Extract<Unit, { kind: "picture" }>): Promise<void> {
    const device = repository.snapshot().deviceId;
    const job = this.begin(unit.lexemeId, unit.label, "render", unit.senseId);
    try {
      const overrides = unit.prompt === undefined && unit.styleId === undefined
        ? {}
        : { prompt: unit.prompt, styleId: unit.styleId };
      const replacing = reflectedRef(unit.promptId);
      await backendSession.renderImage(unit.promptId, device, overrides);
      // The reference does not change across a redraw — it is derived from the record — so the
      // cached bytes have to go, or the article keeps showing the picture that was just replaced.
      // After the write, never before: forgetting first would revoke a URL still on screen, and
      // the picture is deliberately left visible under the "redrawing" mark while this runs.
      if (replacing) await forget(replacing);
      await syncEngine.syncNow();
      this.rest.image = FIRST_REST;
      this.finish(job);
    } catch (error) {
      this.finish(job, message(error));
      await this.rested(error, "image");
    }
  }

  /**
   * One word: find its clips, then brief the senses that have none and draw them one at a time.
   *
   * Clips first, and that ordering is the point rather than an accident: one search and one text
   * call is the faster half by a wide margin, and the owner is looking at the page. Pictures take
   * thirty to sixty seconds each and a provider allows roughly one a minute.
   *
   * Sequential throughout, for the same reason: two at once buys a 429 rather than a second answer,
   * and one at a time is what makes the status legible.
   */
  private async word(lexemeId: string, label: string): Promise<void> {
    const device = repository.snapshot().deviceId;

    if (this.needsClips(lexemeId) && await this.searchIsOn()) {
      const job = this.begin(lexemeId, label, "clips", null, "clip");
      try {
        await backendSession.findClips(device, lexemeId);
        await syncEngine.syncNow();
        this.rest.clip = FIRST_REST;
        this.finish(job);
      } catch (error) {
        this.finish(job, message(error));
        // Not fatal to the word: a corpus that is down or a chain that is busy says nothing about
        // whether this word can be *drawn*, and the server's own sweep will find it again — the
        // mark is written only on a successful consultation, which is what makes that safe.
        await this.rested(error, "clip");
      }
    }
    if (this.stopped) return;

    if (!(await this.drawingIsOn())) return;

    if (this.pending(lexemeId).unbriefed) {
      const job = this.begin(lexemeId, label, "brief");
      try {
        await backendSession.briefLexeme(lexemeId, device);
        await syncEngine.syncNow();
        this.finish(job);
      } catch (error) {
        this.finish(job, message(error));
        // Nothing to draw without a brief, so this word is over either way; resting still matters,
        // because the next word in the queue faces the same allowance.
        await this.rested(error, "image");
        return;
      }
    }

    for (const row of this.pending(lexemeId).drawable) {
      if (this.stopped) return;
      const job = this.begin(lexemeId, label, "render", row.senseId);
      try {
        await backendSession.renderImage(row.id, device);
        await syncEngine.syncNow();
        this.rest.image = FIRST_REST;
        this.finish(job);
      } catch (error) {
        this.finish(job, message(error));
        // A rate limit is about the provider, not this sense: rest, then carry on. Giving up on the
        // word would leave its remaining senses to the sweep for no reason.
        if (!(await this.rested(error, "image"))) return;
      }
    }
  }

  /**
   * What this word still needs, read from the replica. A query, never a queue.
   *
   * `unbriefed` is whether any sense has no prompt row at all; `drawable` is the rows that have a
   * brief and no picture and have not been tried. A row that failed is deliberately absent — the
   * sweep retries those, and pressing on here would spend the word's attempts in one burst against
   * whatever just refused.
   */
  private pending(lexemeId: string): { unbriefed: boolean; drawable: { id: string; senseId: string }[] } {
    const graph = repository.snapshot();
    const senses = graph.senses.filter((sense) => !sense.deleted && sense.lexemeId === lexemeId);
    const prompts = graph.imagePrompts.filter((row) => !row.deleted && row.lexemeId === lexemeId);
    const bySense = new Map(prompts.filter((row) => row.senseId).map((row) => [row.senseId!, row]));

    const rows = senses.map((sense) => bySense.get(sense.id));
    return {
      unbriefed: rows.some((row) => row === undefined),
      drawable: rows
        .filter((row) => row && !row.imageRef && !row.suppressed && row.attempts === 0 && row.prompt)
        .map((row) => ({ id: row!.id, senseId: row!.senseId! }))
    };
  }

  private begin(lexemeId: string, label: string, phase: EnrichmentPhase,
                senseId: string | null = null, kind: EnrichmentKind = "image"): EnrichmentJob {
    const job: EnrichmentJob = {
      id: `${lexemeId}:${phase}:${senseId ?? ""}:${Date.now()}`,
      kind, lexemeId, senseId, label, phase, startedAt: Date.now()
    };
    this.update({ active: job });
    return job;
  }

  /**
   * Wait out a provider that is over its allowance, and say whether to keep going.
   *
   * Deliberately not coordinated with the worker sweep: `models/pacing.py` is process-local and the
   * worker is a different container, so there is no shared limiter to share. The chain's own
   * fall-through plus this backoff *is* the pacing, and building a cross-process limiter would be
   * inventing a problem.
   */
  private async rested(error: unknown, kind: EnrichmentKind): Promise<boolean> {
    if (!(error instanceof AcervoApiError) || !RETRY_CODES.has(error.code)) return false;
    const wait = this.rest[kind];
    this.update({ restingUntil: Date.now() + wait });
    await new Promise((resolve) => setTimeout(resolve, wait));
    this.rest[kind] = Math.min(wait * 2, LONGEST_REST);
    this.update({ restingUntil: null });
    return !this.stopped;
  }
}

/** The picture path this row currently points at, read from the replica. Empty when it has none. */
function reflectedRef(promptId: string): string {
  const row = repository.snapshot().imagePrompts.find((record) => record.id === promptId);
  return row?.imageRef ?? "";
}

function message(error: unknown): string {
  if (error instanceof AcervoApiError) return error.message;
  return error instanceof Error ? error.message : "That picture could not be drawn.";
}

export const enrichment = new EnrichmentEngine();

/** What `App.tsx` calls after a save. Separate so the caller never touches the engine's internals. */
export function enrichSavedWord(lexemeId: string, label: string): void {
  enrichment.enqueue(lexemeId, label);
}

export type { ImagePromptRow };
