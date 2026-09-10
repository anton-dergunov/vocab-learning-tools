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
import { repository } from "./repository";
import { syncEngine } from "./sync";

/** Typed for what comes next. Audio is a second `kind`, not a second engine. */
export type EnrichmentKind = "image" | "audio";
export type EnrichmentPhase = "brief" | "render";

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

export interface EnrichmentStatus {
  /** The unit being worked on right now, or nothing. Strictly one at a time. */
  active: EnrichmentJob | null;
  /** Words queued behind it, in order. */
  waiting: number;
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
  active: null, waiting: 0, recent: [], restingUntil: null, running: false
};

class EnrichmentEngine {
  private status: EnrichmentStatus = EMPTY;
  private listeners = new Set<() => void>();
  private queue: { lexemeId: string; label: string }[] = [];
  private working: Promise<void> | null = null;
  private rest = FIRST_REST;
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
    if (this.status.active?.lexemeId === lexemeId) return;
    if (this.queue.some((item) => item.lexemeId === lexemeId)) return;
    this.queue.push({ lexemeId, label });
    this.update({ waiting: this.queue.length });
    void this.run();
  }

  /** Stop after the unit in flight. Used when signing out — never mid-call, which would waste it. */
  stop(): void {
    this.stopped = true;
    this.queue = [];
    this.update({ waiting: 0 });
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
      this.update({ running: false, active: null, waiting: this.queue.length });
    });
    this.update({ running: true });
    return this.working;
  }

  private async drain(): Promise<void> {
    while (!this.stopped) {
      const next = this.queue.shift();
      if (!next) return;
      this.update({ waiting: this.queue.length });
      await this.word(next.lexemeId, next.label);
    }
  }

  /**
   * One word: brief the senses that have none, then draw them one at a time.
   *
   * Sequential on purpose. Providers meter roughly one image a minute, so two at once buys a 429
   * rather than a second picture — and one at a time is what makes the status legible.
   */
  private async word(lexemeId: string, label: string): Promise<void> {
    const device = repository.snapshot().deviceId;

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
        await this.rested(error);
        return;
      }
    }

    for (const row of this.pending(lexemeId).drawable) {
      if (this.stopped) return;
      const job = this.begin(lexemeId, label, "render", row.senseId);
      try {
        await backendSession.renderImage(row.id, device);
        await syncEngine.syncNow();
        this.rest = FIRST_REST;
        this.finish(job);
      } catch (error) {
        this.finish(job, message(error));
        // A rate limit is about the provider, not this sense: rest, then carry on. Giving up on the
        // word would leave its remaining senses to the sweep for no reason.
        if (!(await this.rested(error))) return;
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
                senseId: string | null = null): EnrichmentJob {
    const job: EnrichmentJob = {
      id: `${lexemeId}:${phase}:${senseId ?? ""}:${Date.now()}`,
      kind: "image", lexemeId, senseId, label, phase, startedAt: Date.now()
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
  private async rested(error: unknown): Promise<boolean> {
    if (!(error instanceof AcervoApiError) || !RETRY_CODES.has(error.code)) return false;
    const until = Date.now() + this.rest;
    this.update({ restingUntil: until });
    await new Promise((resolve) => setTimeout(resolve, this.rest));
    this.rest = Math.min(this.rest * 2, LONGEST_REST);
    this.update({ restingUntil: null });
    return !this.stopped;
  }
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
