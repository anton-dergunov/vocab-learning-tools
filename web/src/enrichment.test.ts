import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AcervoApiError, backendSession, type ImagePromptRow } from "./api";
import { enrichment } from "./enrichment";
import { repository } from "./repository";
import { syncEngine } from "./sync";
import { TEST_OWNER, testGraph } from "./testGraph";

vi.mock("./media", () => ({ forget: vi.fn(async () => undefined) }));

/**
 * The engine drives the two routes; the *rows* it produces arrive the ordinary way, on the next
 * sync pull. So `syncNow` is stubbed to apply what the fake server would have stored, which is what
 * makes "it stops when the work is done" a real assertion rather than a stubbed one.
 */

const DEVICE = () => repository.snapshot().deviceId;

function row(overrides: Partial<ImagePromptRow> = {}): ImagePromptRow {
  return {
    id: "imagepicar00010", lexemeId: "lexemepicar0001", senseId: "sensepicaritch0",
    exampleId: null, prompt: "a nose", styleId: "oil-painting", seed: 1, modelId: "m",
    promptVersion: "v", imageRef: null, imageModelId: null, attempts: 0, failureReason: null,
    suppressed: false, composedPrompt: null, ...overrides
  };
}

/** Rewrites the replica the way a pull would, so the engine's next query sees the new state. */
function serverHolds(rows: ImagePromptRow[]) {
  return vi.spyOn(syncEngine, "syncNow").mockImplementation(async () => {
    const graph = repository.snapshot();
    rows.forEach((incoming) => {
      const held = graph.imagePrompts.find((record) => record.id === incoming.id);
      if (held) Object.assign(held, incoming);
    });
    return syncEngine.getStatus();
  });
}

async function settled() {
  // The engine returns immediately and works behind its status; this is how a test waits it out.
  for (let turn = 0; turn < 200 && enrichment.getStatus().running; turn += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

describe("enriching a word that was just saved", () => {
  beforeEach(async () => {
    await repository.clear();
    await repository.load(TEST_OWNER);
    const graph = testGraph();
    await repository.applyRemote(graph, 1, "dataset00000001");
    enrichment.resume();
    vi.spyOn(syncEngine, "syncNow").mockResolvedValue(syncEngine.getStatus());
    // Automatic work asks the server whether the owner wants pictures drawn at all.
    vi.spyOn(backendSession, "imageSettings").mockResolvedValue({
      drawEnabled: true, stylesOff: [], boostVariety: true, chosen: false,
      maxAttempts: 4, styles: [], available: true
    });
    vi.spyOn(backendSession, "clipSettings").mockResolvedValue({
      searchEnabled: true, selfContainedOnly: false, chosen: false,
      corpus: { configured: true, reachable: true, ready: true, indexedLanguages: ["es"] }
    });
  });

  afterEach(() => { enrichment.stop(); enrichment.resume(); vi.restoreAllMocks(); });

  it("briefs the word once, then draws each sense that has none", async () => {
    const brief = vi.spyOn(backendSession, "briefLexeme")
      .mockResolvedValue({ lexemeId: "lexemepicar0001", imagePrompts: [] });
    const render = vi.spyOn(backendSession, "renderImage")
      .mockResolvedValue(row({ imageRef: "images/a.webp", imageModelId: "painter", attempts: 1 }));
    serverHolds([row({ imageRef: "images/a.webp", imageModelId: "painter", attempts: 1 })]);

    enrichment.enqueue("lexemepicar0001", "picar");
    await settled();

    // The fixture's other sense has no prompt row, so the word needs briefing.
    expect(brief).toHaveBeenCalledWith("lexemepicar0001", DEVICE());
    expect(brief).toHaveBeenCalledTimes(1);
    // Nothing drawable in the replica after the brief, because the fake server wrote no new rows.
    expect(render).not.toHaveBeenCalled();
  });

  it("draws a sense whose brief is already in the replica, without briefing again", async () => {
    const graph = repository.snapshot();
    // Give the word's only sense-less prompt a brief and no picture, and remove the second sense so
    // nothing is unbriefed.
    await repository.applyRemote(
      { senses: graph.senses.filter((sense) => sense.lexemeId !== "lexemepicar0001" || sense.id === "sensepicaritch0"),
        imagePrompts: [{ ...graph.imagePrompts[0], imageRef: null, imageModelId: null, attempts: 0, revision: 99 }] },
      99, "dataset00000001"
    );
    const stale = repository.snapshot().senses.filter(
      (sense) => sense.lexemeId === "lexemepicar0001" && sense.id !== "sensepicaritch0"
    );
    await repository.applyRemote(
      { senses: stale.map((sense) => ({ ...sense, deleted: true, revision: 200 })) }, 200, "dataset00000001"
    );

    const brief = vi.spyOn(backendSession, "briefLexeme");
    const render = vi.spyOn(backendSession, "renderImage")
      .mockResolvedValue(row({ imageRef: "images/a.webp", imageModelId: "painter", attempts: 1 }));
    serverHolds([row({ imageRef: "images/a.webp", imageModelId: "painter", attempts: 1 })]);

    enrichment.enqueue("lexemepicar0001", "picar");
    await settled();

    expect(brief).not.toHaveBeenCalled();
    expect(render).toHaveBeenCalledWith("imagepicar00010", DEVICE());
    expect(render).toHaveBeenCalledTimes(1);
  });

  it("does not queue the same word twice", async () => {
    const brief = vi.spyOn(backendSession, "briefLexeme")
      .mockResolvedValue({ lexemeId: "lexemepicar0001", imagePrompts: [] });
    enrichment.enqueue("lexemepicar0001", "picar");
    enrichment.enqueue("lexemepicar0001", "picar");
    await settled();
    expect(brief).toHaveBeenCalledTimes(1);
  });

  it("keeps a failure in view with the provider's own words", async () => {
    vi.spyOn(backendSession, "briefLexeme").mockRejectedValue(
      new AcervoApiError("The language model refused the request.", 502, "llm_failed")
    );
    enrichment.enqueue("lexemepicar0001", "picar");
    await settled();

    const [latest] = enrichment.getStatus().recent;
    expect(latest.phase).toBe("brief");
    expect(latest.error).toBe("The language model refused the request.");
    expect(enrichment.getStatus().active).toBeNull();
  });

  it("draws one picture the owner asked for, with the words they typed", async () => {
    const render = vi.spyOn(backendSession, "renderImage")
      .mockResolvedValue(row({ imageRef: "images/a.webp", imageModelId: "painter", attempts: 2 }));
    const brief = vi.spyOn(backendSession, "briefLexeme");

    enrichment.redraw({
      lexemeId: "lexemepicar0001", senseId: "sensepicaritch0", promptId: "imagepicar00010",
      label: "picar", prompt: "Dog with a sausage", styleId: "folk-naive"
    });
    await settled();

    expect(brief).not.toHaveBeenCalled();
    expect(render).toHaveBeenCalledWith("imagepicar00010", DEVICE(),
      { prompt: "Dog with a sausage", styleId: "folk-naive" });
    // It goes through the one queue rather than straight at the route, so a hand-asked redraw shows
    // up beside the automatic work and cannot race it against a one-a-minute provider.
    const [latest] = enrichment.getStatus().recent;
    expect(latest).toMatchObject({ phase: "render", senseId: "sensepicaritch0", label: "picar" });
    expect(latest.error).toBeUndefined();
  });

  it("never discards a changed brief, even for a picture already on its way", async () => {
    // The dialog closes on Draw, so asking twice means reopening it and typing — a deliberate act.
    // Dropping that silently would be a worse failure than drawing one picture twice.
    const render = vi.spyOn(backendSession, "renderImage")
      .mockResolvedValue(row({ imageRef: "images/a.webp", imageModelId: "painter" }));
    const ask = (prompt: string) => enrichment.redraw({
      lexemeId: "lexemepicar0001", senseId: "sensepicaritch0", promptId: "imagepicar00010",
      label: "picar", prompt, styleId: "folk-naive"
    });
    ask("Dog with a sausage");
    ask("A sausage, enormous");
    await settled();

    expect(render).toHaveBeenCalledTimes(2);
    expect(render).toHaveBeenLastCalledWith("imagepicar00010", DEVICE(),
      { prompt: "A sausage, enormous", styleId: "folk-naive" });
  });

  it("collapses an identical request that is still queued", async () => {
    const render = vi.spyOn(backendSession, "renderImage")
      .mockImplementation(async () => {
        await new Promise((resolve) => setTimeout(resolve, 0));
        return row({ imageRef: "images/a.webp", imageModelId: "painter" });
      });
    const ask = (senseId: string, promptId: string) => enrichment.redraw({
      lexemeId: "lexemepicar0001", senseId, promptId, label: "picar",
      prompt: "Dog with a sausage", styleId: "folk-naive"
    });
    // The first starts at once; the next two queue behind it, and the third is the second again.
    ask("sensepicaritch0", "imagepicar00010");
    ask("sensepicarchop0", "imagepicar00020");
    ask("sensepicarchop0", "imagepicar00020");
    await settled();

    expect(render.mock.calls.map((call) => call[0])).toEqual(["imagepicar00010", "imagepicar00020"]);
  });

  it("forgets the cached picture after the write, so the article stops showing the old one", async () => {
    // The path is derived from the record and so does not change across a redraw. Without this the
    // article kept serving the cached bytes until it happened to remount — which is what "close the
    // word and open it again" was working around.
    const { forget } = await import("./media");
    vi.spyOn(backendSession, "renderImage")
      .mockResolvedValue(row({ imageRef: "images/a.webp", imageModelId: "painter" }));

    enrichment.redraw({
      lexemeId: "lexemepicar0001", senseId: "sensepicaritch0", promptId: "imagepicar00010",
      label: "picar"
    });
    await settled();
    expect(forget).toHaveBeenCalledWith("images/lexemepicar0001/imagepicar00010.webp");
  });

  it("comes back to the sense the provider was too busy to draw", async () => {
    /* The bug this closes, seen in production: a 429 on the image call left the sense with a brief,
       no picture and `attempts: 0` — still drawable by this engine's own rule — and nothing looked
       again, because a word is only enqueued when it is saved. Two senses read as "waiting" for ten
       minutes while the same provider drew the next word's pictures.

       The engine already *rested* thirty seconds for that row; it simply walked on through a list
       captured before the wait and then finished the word. The server deliberately does not count a
       rate limit against the sense (`render_prompt` raises without writing), so coming back is safe
       and is exactly what the rest was paid for. */
    const graph = repository.snapshot();
    await repository.applyRemote(
      { senses: graph.senses.filter((sense) => sense.lexemeId !== "lexemepicar0001" || sense.id === "sensepicaritch0"),
        imagePrompts: [{ ...graph.imagePrompts[0], imageRef: null, imageModelId: null, attempts: 0, revision: 99 }] },
      99, "dataset00000001"
    );
    const stale = repository.snapshot().senses.filter(
      (sense) => sense.lexemeId === "lexemepicar0001" && sense.id !== "sensepicaritch0"
    );
    await repository.applyRemote(
      { senses: stale.map((sense) => ({ ...sense, deleted: true, revision: 200 })) }, 200, "dataset00000001"
    );

    vi.useFakeTimers();
    try {
      const render = vi.spyOn(backendSession, "renderImage")
        .mockRejectedValueOnce(new AcervoApiError("busy", 503, "llm_rate_limited"))
        .mockResolvedValue(row({ imageRef: "images/a.webp", imageModelId: "painter", attempts: 1 }));

      enrichment.enqueue("lexemepicar0001", "picar");
      // Unconditionally rather than `while (running)`: the engine has not started on the first tick.
      for (let turn = 0; turn < 60; turn += 1) await vi.advanceTimersByTimeAsync(5_000);

      // Asked for again after the rest, rather than left for the server's sweep with the thirty
      // seconds already spent on its behalf.
      expect(render.mock.calls.length).toBeGreaterThan(1);
      expect(render.mock.calls.every((call) => call[0] === "imagepicar00010")).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it("draws nothing on its own once the owner switches drawing off", async () => {
    // The bug this closes: the switch used to gate only the server's sweep, so saving a word still
    // produced pictures with it off. The setting lives on the server, so it is asked rather than
    // cached — a stale copy would either draw for someone who had switched it off or refuse to
    // draw for someone who never opened Settings.
    vi.spyOn(backendSession, "imageSettings").mockResolvedValue({
      drawEnabled: false, stylesOff: [], boostVariety: true, chosen: true,
      maxAttempts: 4, styles: [], available: true
    });
    const brief = vi.spyOn(backendSession, "briefLexeme");
    const render = vi.spyOn(backendSession, "renderImage");

    enrichment.enqueue("lexemepicar0001", "picar");
    await settled();

    expect(brief).not.toHaveBeenCalled();
    expect(render).not.toHaveBeenCalled();
  });

  it("still draws a picture the owner asks for by hand with drawing switched off", async () => {
    // Switching it off is how you get a word with no pictures and then add the one you want.
    vi.spyOn(backendSession, "imageSettings").mockResolvedValue({
      drawEnabled: false, stylesOff: [], boostVariety: true, chosen: true,
      maxAttempts: 4, styles: [], available: true
    });
    const render = vi.spyOn(backendSession, "renderImage")
      .mockResolvedValue(row({ imageRef: "images/a.webp", imageModelId: "painter" }));

    enrichment.redraw({
      lexemeId: "lexemepicar0001", senseId: "sensepicaritch0", promptId: "imagepicar00010",
      label: "picar", prompt: "Dog with a sausage", styleId: "folk-naive"
    });
    await settled();

    expect(render).toHaveBeenCalledTimes(1);
  });

  it("draws nothing on its own when the server cannot be asked", async () => {
    /* Unreachable means no. Nothing can be drawn without the server anyway, so this costs only the
       decision — and the sweep picks the word up later regardless. */
    vi.spyOn(backendSession, "imageSettings").mockRejectedValue(new Error("offline"));
    const brief = vi.spyOn(backendSession, "briefLexeme");
    enrichment.enqueue("lexemepicar0001", "picar");
    await settled();
    expect(brief).not.toHaveBeenCalled();
  });

  it("stops without a call once the owner signs out", async () => {
    const brief = vi.spyOn(backendSession, "briefLexeme")
      .mockResolvedValue({ lexemeId: "lexemepicar0001", imagePrompts: [] });
    enrichment.stop();
    enrichment.enqueue("lexemepicar0001", "picar");
    await settled();
    expect(brief).not.toHaveBeenCalled();
  });
});


/**
 * The third kind. Clips go through the same queue, in the same word unit, ahead of the picture
 * work — `docs/plans/spoken-clips.md` §2.11: it is a third `kind`, not a second engine.
 */
describe("finding clips for a word that was just saved", () => {
  beforeEach(async () => {
    await repository.clear();
    await repository.load(TEST_OWNER);
    await repository.applyRemote(testGraph(), 1, "dataset00000001");
    enrichment.resume();
    vi.spyOn(syncEngine, "syncNow").mockResolvedValue(syncEngine.getStatus());
    vi.spyOn(backendSession, "imageSettings").mockResolvedValue({
      drawEnabled: false, stylesOff: [], boostVariety: true, chosen: true,
      maxAttempts: 4, styles: [], available: true
    });
    vi.spyOn(backendSession, "clipSettings").mockResolvedValue({
      searchEnabled: true, selfContainedOnly: false, chosen: false,
      corpus: { configured: true, reachable: true, ready: true, indexedLanguages: ["es"] }
    });
  });

  afterEach(() => { enrichment.stop(); enrichment.resume(); vi.restoreAllMocks(); });

  const found = (overrides = {}) => ({
    lexemeId: "lexemebalsa0001", searched: true, skipped: null, examples: [], dropped: 0,
    usage: null, ...overrides
  });

  it("searches a word that has never been through one", async () => {
    // `lexemebalsa0001` carries a null `clipsSearchedAt`, which is what "never consulted" looks
    // like — and is what an imported word looks like too.
    const find = vi.spyOn(backendSession, "findClips").mockResolvedValue(found());

    enrichment.enqueue("lexemebalsa0001", "la balsa");
    await settled();

    expect(find).toHaveBeenCalledWith(DEVICE(), "lexemebalsa0001");
    expect(find).toHaveBeenCalledTimes(1);
  });

  it("leaves a word alone once it has been consulted, however thin the answer was", async () => {
    // The fixture's `picar` was searched on 24 August and holds one clip; a word searched and found
    // empty looks the same to this query, and must not be re-asked. The search is one-shot at save.
    const find = vi.spyOn(backendSession, "findClips");

    enrichment.enqueue("lexemepicar0001", "picar");
    await settled();

    expect(find).not.toHaveBeenCalled();
  });

  it("does not search when the owner has switched save-time searching off", async () => {
    vi.spyOn(backendSession, "clipSettings").mockResolvedValue({
      searchEnabled: false, selfContainedOnly: false, chosen: true, corpus: { configured: true, reachable: true }
    });
    const find = vi.spyOn(backendSession, "findClips");

    enrichment.enqueue("lexemebalsa0001", "la balsa");
    await settled();

    expect(find).not.toHaveBeenCalled();
  });

  it("searches before it draws, because the owner is looking at the page", async () => {
    const order: string[] = [];
    vi.spyOn(backendSession, "imageSettings").mockResolvedValue({
      drawEnabled: true, stylesOff: [], boostVariety: true, chosen: true,
      maxAttempts: 4, styles: [], available: true
    });
    vi.spyOn(backendSession, "findClips").mockImplementation(async () => {
      order.push("clips");
      return found();
    });
    vi.spyOn(backendSession, "briefLexeme").mockImplementation(async () => {
      order.push("brief");
      return { lexemeId: "lexemebalsa0001", imagePrompts: [] };
    });

    enrichment.enqueue("lexemebalsa0001", "la balsa");
    await settled();

    expect(order).toEqual(["clips", "brief"]);
  });

  it("carries on to the pictures when the corpus is down", async () => {
    // A corpus that cannot be reached says nothing about whether the word can be drawn, and the
    // server's sweep will find it again — the mark is written only on a successful consultation.
    vi.spyOn(backendSession, "imageSettings").mockResolvedValue({
      drawEnabled: true, stylesOff: [], boostVariety: true, chosen: true,
      maxAttempts: 4, styles: [], available: true
    });
    vi.spyOn(backendSession, "findClips")
      .mockRejectedValue(new AcervoApiError("no corpus", 502, "corpus_unreachable"));
    const brief = vi.spyOn(backendSession, "briefLexeme")
      .mockResolvedValue({ lexemeId: "lexemebalsa0001", imagePrompts: [] });

    enrichment.enqueue("lexemebalsa0001", "la balsa");
    await settled();

    expect(brief).toHaveBeenCalled();
    expect(enrichment.getStatus().recent.some((job) => job.kind === "clip" && job.error)).toBe(true);
  });

  it("shows the search as its own kind of work", async () => {
    vi.spyOn(backendSession, "findClips").mockResolvedValue(found());

    enrichment.enqueue("lexemebalsa0001", "la balsa");
    await settled();

    const job = enrichment.getStatus().recent.find((one) => one.phase === "clips");
    expect(job?.kind).toBe("clip");
    expect(job?.senseId).toBeNull();      // one search covers every sense of the word
    expect(job?.error).toBeUndefined();
  });
});
