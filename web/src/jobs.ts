import { AcervoApiError, backendSession, type Job } from "./api";
import { syncEngine } from "./sync";

/**
 * What the server is doing, as this device last heard it (`docs/architecture/server.md`, "Jobs").
 *
 * The interface shows work and never does it. This module reads the server's event stream, keeps
 * the latest job for each subject, and asks for a pull whenever the server says its revision moved —
 * so a picture drawn on the server lands through the one path every record takes.
 *
 * Nothing here is needed to read: without the stream the 60-second pull still converges, and the
 * progress strip simply updates less often. After every (re)connect the map is rebuilt from
 * `GET /jobs?open=true`, because a job that finished while the stream was down sent its news to
 * nobody.
 */

export interface JobsStatus {
  /** The latest job this device knows of per kind and subject (`jobKey`), open or finished. */
  bySubject: ReadonlyMap<string, Job>;
  connected: boolean;
}

const OPEN = new Set(["queued", "running"]);
const FIRST_RETRY = 1_000;
const LONGEST_RETRY = 30_000;

export const isOpen = (job: Job | undefined | null): job is Job & { state: "queued" | "running" } =>
  Boolean(job && OPEN.has(job.state));

/**
 * Whether a story's job still has its recording to do: it is open and that step has neither run nor
 * been skipped. A part with no recording is then about to get one from the job, and asking for it
 * again on demand would record it twice.
 */
export function isRecording(job: Job | undefined | null): boolean {
  if (!isOpen(job)) return false;
  const step = job.steps.find((one) => one.name === "story.audio");
  return step !== undefined && ["pending", "running", "waiting"].includes(step.state);
}

/** Jobs are kept per kind *and* subject: a new brief for a word must not hide its enrichment. */
export const jobKey = (kind: string, subjectId: string) => `${kind}:${subjectId}`;

/** The latest job of one kind about one record, open or just finished. */
export function jobFor(status: JobsStatus, kind: string, subjectId: string): Job | undefined {
  return status.bySubject.get(jobKey(kind, subjectId));
}

/** The job a word's page shows: its enrichment, open or just finished. */
export function enrichmentOf(status: JobsStatus, lexemeId: string): Job | undefined {
  return jobFor(status, "enrich", lexemeId);
}

/** Whether a word is still filling in. */
export function isEnriching(status: JobsStatus, lexemeId: string): boolean {
  return isOpen(enrichmentOf(status, lexemeId));
}

const UNFINISHED_STEP = new Set(["pending", "running", "waiting"]);

/**
 * Where a word's clip search stands, from its enrichment job and the replica's own mark.
 *
 * A search that found something stays "searching" until the pull brings the clip — the job's news
 * arrives before its records do, and saying "nothing" in between would be a line that jumps.
 */
export function clipSearchOf(
  job: Job | undefined, clipsSearchedAt: string | null
): "searching" | "none" | "failed" | null {
  if (!job || job.kind !== "enrich") return null;
  const step = job.steps.find((entry) => entry.name === "clips");
  if (!step) return isOpen(job) && clipsSearchedAt === null ? "searching" : null;
  if (UNFINISHED_STEP.has(step.state)) return clipsSearchedAt === null ? "searching" : null;
  if (step.state === "failed") return "failed";
  if (step.state === "done") {
    return Number(step.detail?.found ?? 0) > 0 && clipsSearchedAt === null ? "searching" : "none";
  }
  return null;
}

/** Whether a word's pictures are still ahead of its enrichment. */
export function drawingPictures(job: Job | undefined): boolean {
  if (!isOpen(job) || job.kind !== "enrich") return false;
  const step = job.steps.find((entry) => entry.name === "pictures");
  return !step || UNFINISHED_STEP.has(step.state);
}

type Sleep = (milliseconds: number, signal: AbortSignal) => Promise<void>;

const sleep: Sleep = (milliseconds, signal) => new Promise((resolve) => {
  const timer = setTimeout(resolve, milliseconds);
  signal.addEventListener("abort", () => { clearTimeout(timer); resolve(); }, { once: true });
});

/** Splits a server-sent-events body into `{event, data}` frames, carrying partial ones over. */
export class FrameReader {
  private buffer = "";

  push(text: string): { event: string; data: string }[] {
    this.buffer += text.replace(/\r\n/g, "\n");
    const frames: { event: string; data: string }[] = [];
    let boundary = this.buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(boundary + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith(":")) continue;
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
      }
      if (data.length) frames.push({ event, data: data.join("\n") });
      boundary = this.buffer.indexOf("\n\n");
    }
    return frames;
  }
}

export class JobStream {
  private status: JobsStatus = { bySubject: new Map(), connected: false };
  private listeners = new Set<() => void>();
  private controller: AbortController | null = null;

  constructor(private readonly wait: Sleep = sleep) {}

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  getStatus = (): JobsStatus => this.status;

  /** Keeps a stream open until `stop`, reconnecting with backoff. Tests drive `run` themselves. */
  start(): void {
    this.stop();
    if (import.meta.env.MODE === "test") return;
    void this.run();
  }

  stop(): void {
    this.controller?.abort();
    this.controller = null;
    this.update({ bySubject: new Map(), connected: false });
  }

  /** Connect, and reconnect whenever the stream drops, until stopped or signed out. */
  async run(): Promise<void> {
    const controller = new AbortController();
    this.controller = controller;
    let delay = FIRST_RETRY;
    while (!controller.signal.aborted) {
      try {
        const heard = await this.connect(controller.signal);
        if (heard) delay = FIRST_RETRY;
      } catch (error) {
        if (error instanceof AcervoApiError && error.status === 401) break;
      }
      if (controller.signal.aborted) break;
      this.update({ connected: false });
      await this.wait(delay, controller.signal);
      delay = Math.min(delay * 2, LONGEST_RETRY);
    }
  }

  /** One connection, read to its end. True when the server said it was live. */
  async connect(signal: AbortSignal): Promise<boolean> {
    const response = await backendSession.events(signal);
    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    const frames = new FrameReader();
    let live = false;
    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        for (const frame of frames.push(decoder.decode(value, { stream: true }))) {
          if (frame.event === "ready") {
            live = true;
            await this.rebuild();
            this.update({ connected: true });
            // Whatever changed while nobody was listening.
            void syncEngine.syncNow();
          } else if (frame.event === "job") {
            this.apply((JSON.parse(frame.data) as { job: Job }).job);
          } else if (frame.event === "revision") {
            void syncEngine.syncNow();
          }
        }
      }
    } catch (error) {
      if (!signal.aborted) throw error;
    } finally {
      reader.releaseLock?.();
    }
    return live;
  }

  /** The open jobs, as the server holds them now. Finished ones this device already saw are kept. */
  async rebuild(): Promise<void> {
    const open = await backendSession.jobs(true);
    const next = new Map<string, Job>();
    this.status.bySubject.forEach((job, key) => {
      // A job this device saw open and the server no longer lists has finished unseen; its final
      // state is fetched rather than guessed, so a failure still shows its Try again.
      if (!isOpen(job)) next.set(key, job);
    });
    const vanished = [...this.status.bySubject.values()].filter(
      (job) => isOpen(job) && !open.some((current) => current.id === job.id)
    );
    for (const job of open) if (job.subject) next.set(jobKey(job.kind, job.subject.id), job);
    this.update({ bySubject: next });
    for (const job of vanished) {
      try { this.apply(await backendSession.job(job.id)); } catch { /* pruned or gone: leave it */ }
    }
  }

  /** One job's news. The newest job for a subject wins, so a Try again replaces the failure. */
  apply(job: Job): void {
    if (!job.subject) return;
    const key = jobKey(job.kind, job.subject.id);
    const held = this.status.bySubject.get(key);
    if (held && held.id !== job.id && held.createdAt > job.createdAt) return;
    const next = new Map(this.status.bySubject);
    if (job.dismissed) next.delete(key);
    else next.set(key, job);
    this.update({ bySubject: next });
  }

  /** The owner has seen a finished job's outcome and left the word; stop showing it. */
  forget(kind: string, subjectId: string): void {
    const key = jobKey(kind, subjectId);
    const held = this.status.bySubject.get(key);
    if (!held || isOpen(held)) return;
    const next = new Map(this.status.bySubject);
    next.delete(key);
    this.update({ bySubject: next });
  }

  private update(changes: Partial<JobsStatus>): void {
    this.status = { ...this.status, ...changes };
    this.listeners.forEach((listener) => listener());
  }
}

export const jobStream = new JobStream();
