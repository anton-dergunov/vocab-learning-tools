import { afterEach, describe, expect, it, vi } from "vitest";
import { AcervoApiError, backendSession, type Job } from "./api";
import {
  FrameReader, JobStream, clipSearchOf, drawingPictures, enrichmentOf, isEnriching, jobFor
} from "./jobs";
import { syncEngine } from "./sync";

function job(overrides: Partial<Job> = {}): Job {
  return {
    id: "job000000000001", ownerId: "owner0000000001", parentId: null, kind: "enrich",
    subject: { kind: "lexeme", id: "lexemepicar0001" }, input: {}, state: "queued",
    trigger: "save", steps: [], rerun: false, cancelRequested: false, dismissed: false,
    error: null, message: null, notBefore: null, createdAt: "2026-09-17T10:00:00.000Z",
    startedAt: null, finishedAt: null, ...overrides
  };
}

const frame = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

/** A response whose body yields `chunks` and then ends, as a dropped connection does. */
function body(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    }
  });
  return { ok: true, body: stream } as unknown as Response;
}

afterEach(() => { vi.restoreAllMocks(); });

describe("reading server-sent events", () => {
  it("splits frames, skips comments and carries a partial frame over", () => {
    const reader = new FrameReader();
    expect(reader.push(": still here\n\nevent: revision\ndata: {\"cursor\"")).toEqual([]);
    expect(reader.push(":3}\n\nevent: ready\ndata: {}\n\n")).toEqual([
      { event: "revision", data: "{\"cursor\":3}" },
      { event: "ready", data: "{}" }
    ]);
  });
});

describe("the job stream", () => {
  it("rebuilds from the open jobs once live, and pulls for what it missed", async () => {
    const pulls = vi.spyOn(syncEngine, "syncNow").mockResolvedValue(syncEngine.getStatus());
    vi.spyOn(backendSession, "jobs").mockResolvedValue([job()]);
    vi.spyOn(backendSession, "events").mockResolvedValue(body([frame("ready", { type: "ready" })]));
    const stream = new JobStream();
    const heard: boolean[] = [];
    stream.subscribe(() => heard.push(stream.getStatus().connected));

    expect(await stream.connect(new AbortController().signal)).toBe(true);
    expect(isEnriching(stream.getStatus(), "lexemepicar0001")).toBe(true);
    expect(heard).toContain(true);
    expect(pulls).toHaveBeenCalledTimes(1);
  });

  it("keeps each word's latest job from the events, and pulls on a revision", async () => {
    const pulls = vi.spyOn(syncEngine, "syncNow").mockResolvedValue(syncEngine.getStatus());
    vi.spyOn(backendSession, "jobs").mockResolvedValue([]);
    const running = job({ state: "running", steps: [{ name: "clips", state: "running" }] });
    vi.spyOn(backendSession, "events").mockResolvedValue(body([
      frame("ready", { type: "ready" }),
      frame("job", { type: "job", job: job() }),
      frame("job", { type: "job", job: running }),
      frame("revision", { type: "revision", cursor: 9 })
    ]));
    const stream = new JobStream();
    await stream.connect(new AbortController().signal);

    const held = enrichmentOf(stream.getStatus(), "lexemepicar0001");
    expect(held?.state).toBe("running");
    expect(held?.steps[0].name).toBe("clips");
    expect(pulls).toHaveBeenCalledTimes(2);
  });

  it("recovers from a dropped stream through the open-job list", async () => {
    vi.spyOn(syncEngine, "syncNow").mockResolvedValue(syncEngine.getStatus());
    const open = job({ state: "running" });
    const failed = job({ state: "failed", error: "image_refused" });
    vi.spyOn(backendSession, "jobs")
      .mockResolvedValueOnce([open])
      .mockResolvedValueOnce([]);
    const fetched = vi.spyOn(backendSession, "job").mockResolvedValue(failed);
    const stream = new JobStream(async () => undefined);
    let connections = 0;
    vi.spyOn(backendSession, "events").mockImplementation(async () => {
      connections += 1;
      if (connections === 3) {
        stream.stop();
        throw new AcervoApiError("gone", 0, "offline");
      }
      // Live, and then dropped: the job finishes while nobody is listening.
      return body([frame("ready", { type: "ready" })]);
    });
    // `stop` clears the map, so read it the moment the second connection has rebuilt.
    const seen: (string | undefined)[] = [];
    stream.subscribe(() => seen.push(enrichmentOf(stream.getStatus(), "lexemepicar0001")?.state));

    await stream.run();

    expect(connections).toBe(3);
    expect(fetched).toHaveBeenCalledWith(open.id);
    expect(seen).toContain("running");
    expect(seen).toContain("failed");
    expect(seen.lastIndexOf("failed")).toBeGreaterThan(seen.indexOf("running"));
  });

  it("stops trying once the server says the session is over", async () => {
    const events = vi.spyOn(backendSession, "events")
      .mockRejectedValue(new AcervoApiError("Sign in", 401, "unauthenticated"));
    const stream = new JobStream(async () => undefined);
    await stream.run();
    expect(events).toHaveBeenCalledTimes(1);
  });

  it("waits longer after each failed connection", async () => {
    const waits: number[] = [];
    const stream = new JobStream(async (milliseconds) => { waits.push(milliseconds); });
    vi.spyOn(backendSession, "events").mockImplementation(async () => {
      if (waits.length === 3) stream.stop();
      throw new AcervoApiError("gone", 0, "offline");
    });
    await stream.run();
    expect(waits).toEqual([1_000, 2_000, 4_000]);
  });
});

describe("the map of jobs", () => {
  it("lets a newer job replace an older one, never the other way round", () => {
    const stream = new JobStream();
    const retried = job({ id: "job000000000002", createdAt: "2026-09-17T11:00:00.000Z" });
    stream.apply(retried);
    stream.apply(job({ state: "failed" }));
    expect(enrichmentOf(stream.getStatus(), "lexemepicar0001")?.id).toBe(retried.id);
  });

  it("drops a dismissed job, and forgets a finished one when asked", () => {
    const stream = new JobStream();
    stream.apply(job({ state: "done" }));
    stream.forget("enrich", "lexemepicar0001");
    expect(enrichmentOf(stream.getStatus(), "lexemepicar0001")).toBeUndefined();

    stream.apply(job({ state: "failed" }));
    stream.apply(job({ state: "failed", dismissed: true }));
    expect(enrichmentOf(stream.getStatus(), "lexemepicar0001")).toBeUndefined();
  });

  it("does not forget a job that is still open", () => {
    const stream = new JobStream();
    stream.apply(job());
    stream.forget("enrich", "lexemepicar0001");
    expect(isEnriching(stream.getStatus(), "lexemepicar0001")).toBe(true);
  });

  it("only counts enrichment as a word filling in", () => {
    const stream = new JobStream();
    stream.apply(job({ kind: "image.rebrief" }));
    expect(isEnriching(stream.getStatus(), "lexemepicar0001")).toBe(false);
  });

  it("keeps a new brief for a word beside that word's enrichment, not over it", () => {
    const stream = new JobStream();
    stream.apply(job());
    stream.apply(job({ id: "job000000000009", kind: "image.rebrief", createdAt: "2026-09-17T11:00:00.000Z" }));
    expect(isEnriching(stream.getStatus(), "lexemepicar0001")).toBe(true);
    expect(jobFor(stream.getStatus(), "image.rebrief", "lexemepicar0001")?.id).toBe("job000000000009");
  });
});

describe("reading a word's enrichment", () => {
  const withClips = (state: string, detail?: Record<string, unknown>, jobState: Job["state"] = "running") =>
    job({ state: jobState, steps: [{ name: "clips", state: state as never, detail }] });

  it("holds the clip slot while the search is ahead", () => {
    expect(clipSearchOf(job(), null)).toBe("searching");
    expect(clipSearchOf(withClips("pending"), null)).toBe("searching");
    expect(clipSearchOf(withClips("waiting"), null)).toBe("searching");
  });

  it("keeps holding it until the clip it found has been pulled", () => {
    expect(clipSearchOf(withClips("done", { found: 1 }), null)).toBe("searching");
    expect(clipSearchOf(withClips("done", { found: 1 }), "2026-09-17T10:00:00.000Z")).toBe("none");
  });

  it("settles on nothing found, a failure, or nothing at all", () => {
    expect(clipSearchOf(withClips("done", { found: 0 }, "done"), "2026-09-17T10:00:00.000Z")).toBe("none");
    expect(clipSearchOf(withClips("failed", undefined, "failed"), null)).toBe("failed");
    expect(clipSearchOf(withClips("skipped"), null)).toBeNull();
    expect(clipSearchOf(undefined, null)).toBeNull();
    // A word searched long ago, enriched again for a new sense, has nothing to wait for.
    expect(clipSearchOf(job(), "2026-09-17T10:00:00.000Z")).toBeNull();
  });

  it("says pictures are ahead only while the job is open and their step is unfinished", () => {
    expect(drawingPictures(job())).toBe(true);
    expect(drawingPictures(job({ state: "running", steps: [{ name: "pictures", state: "running" }] }))).toBe(true);
    expect(drawingPictures(job({ state: "running", steps: [{ name: "pictures", state: "done" }] }))).toBe(false);
    expect(drawingPictures(job({ state: "failed", steps: [{ name: "pictures", state: "pending" }] }))).toBe(false);
  });
});
