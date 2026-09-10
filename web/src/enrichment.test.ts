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

  it("stops without a call once the owner signs out", async () => {
    const brief = vi.spyOn(backendSession, "briefLexeme")
      .mockResolvedValue({ lexemeId: "lexemepicar0001", imagePrompts: [] });
    enrichment.stop();
    enrichment.enqueue("lexemepicar0001", "picar");
    await settled();
    expect(brief).not.toHaveBeenCalled();
  });
});
