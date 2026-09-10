import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AcervoApiError, backendSession, type ImagePromptRow } from "./api";
import { enrichment } from "./enrichment";
import { repository } from "./repository";
import { syncEngine } from "./sync";
import { TEST_OWNER, testGraph } from "./testGraph";

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

  it("stops without a call once the owner signs out", async () => {
    const brief = vi.spyOn(backendSession, "briefLexeme")
      .mockResolvedValue({ lexemeId: "lexemepicar0001", imagePrompts: [] });
    enrichment.stop();
    enrichment.enqueue("lexemepicar0001", "picar");
    await settled();
    expect(brief).not.toHaveBeenCalled();
  });
});
